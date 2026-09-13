/*
 * mqtt_sub.c - Lightweight MQTT Subscribe Client for ESP32-S3 Linux
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <netdb.h>
#include <signal.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <poll.h>

#define MQTT_PKT_CONNECT    1
#define MQTT_PKT_CONNACK    2
#define MQTT_PKT_PUBLISH    3
#define MQTT_PKT_PUBACK     4
#define MQTT_PKT_SUBSCRIBE  8
#define MQTT_PKT_SUBACK     9
#define MQTT_PKT_PINGREQ    12
#define MQTT_PKT_PINGRESP   13
#define MQTT_PKT_DISCONNECT 14

static int running = 1;

static void handle_sig(int sig) {
    (void)sig;
    running = 0;
}

static int encode_rem_len(uint8_t *buf, int len) {
    int idx = 0;
    do {
        uint8_t d = len % 128;
        len /= 128;
        if (len > 0) d |= 128;
        buf[idx++] = d;
    } while (len > 0);
    return idx;
}

static int decode_rem_len(const uint8_t *buf, int max_bytes, int *val_out) {
    int multiplier = 1;
    int value = 0;
    int bytes = 0;
    for (int i = 0; i < max_bytes && i < 4; i++) {
        bytes++;
        value += (buf[i] & 127) * multiplier;
        if ((buf[i] & 128) == 0) {
            *val_out = value;
            return bytes;
        }
        multiplier *= 128;
    }
    return -1;
}

static int connect_tcp(const char *host, int port) {
    struct addrinfo hints, *res, *rp;
    char port_str[16];
    snprintf(port_str, sizeof(port_str), "%d", port);

    memset(&hints, 0, sizeof(hints));
    hints.ai_family = AF_UNSPEC;
    hints.ai_socktype = SOCK_STREAM;

    if (getaddrinfo(host, port_str, &hints, &res) != 0) {
        return -1;
    }

    int fd = -1;
    for (rp = res; rp != NULL; rp = rp->ai_next) {
        fd = socket(rp->ai_family, rp->ai_socktype, rp->ai_protocol);
        if (fd == -1) continue;
        if (connect(fd, rp->ai_addr, rp->ai_addrlen) != -1) break;
        close(fd);
        fd = -1;
    }
    freeaddrinfo(res);
    return fd;
}

int main(int argc, char **argv) {
    const char *host = "127.0.0.1";
    int port = 1883;
    const char *topic = NULL;
    int max_count = -1;
    int verbose = 0;
    char client_id[32];
    snprintf(client_id, sizeof(client_id), "sub-%d", (int)getpid());

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-h") == 0 && i + 1 < argc) host = argv[++i];
        else if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) port = atoi(argv[++i]);
        else if (strcmp(argv[i], "-t") == 0 && i + 1 < argc) topic = argv[++i];
        else if (strcmp(argv[i], "-C") == 0 && i + 1 < argc) max_count = atoi(argv[++i]);
        else if (strcmp(argv[i], "-v") == 0) verbose = 1;
        else if (strcmp(argv[i], "-i") == 0 && i + 1 < argc) snprintf(client_id, sizeof(client_id), "%s", argv[++i]);
        else if (strcmp(argv[i], "--help") == 0) {
            printf("Usage: mqtt-sub [-h host] [-p port] -t topic [-C count] [-v]\n");
            return 0;
        }
    }

    if (!topic) {
        fprintf(stderr, "Error: -t <topic> is required\n");
        return 1;
    }

    signal(SIGINT, handle_sig);
    signal(SIGTERM, handle_sig);

    int fd = connect_tcp(host, port);
    if (fd < 0) {
        fprintf(stderr, "Error: Could not connect to %s:%d\n", host, port);
        return 1;
    }

    /* 1. Send CONNECT */
    uint8_t connect_pkt[128];
    int cid_len = strlen(client_id);
    int var_len = 10 + 2 + cid_len;

    connect_pkt[0] = (MQTT_PKT_CONNECT << 4);
    int hlen = 1;
    hlen += encode_rem_len(&connect_pkt[hlen], var_len);

    connect_pkt[hlen++] = 0; connect_pkt[hlen++] = 4;
    connect_pkt[hlen++] = 'M'; connect_pkt[hlen++] = 'Q'; connect_pkt[hlen++] = 'T'; connect_pkt[hlen++] = 'T';
    connect_pkt[hlen++] = 4;
    connect_pkt[hlen++] = 2; /* Clean session */
    connect_pkt[hlen++] = 0; connect_pkt[hlen++] = 60;

    connect_pkt[hlen++] = (cid_len >> 8) & 0xFF;
    connect_pkt[hlen++] = cid_len & 0xFF;
    memcpy(&connect_pkt[hlen], client_id, cid_len);
    hlen += cid_len;

    write(fd, connect_pkt, hlen);

    /* Read CONNACK */
    uint8_t connack[4];
    if (read(fd, connack, 4) < 4 || (connack[0] >> 4) != MQTT_PKT_CONNACK || connack[3] != 0) {
        fprintf(stderr, "Error: MQTT connection refused\n");
        close(fd);
        return 1;
    }

    /* 2. Send SUBSCRIBE */
    uint8_t sub_pkt[128];
    int tlen = strlen(topic);
    int sub_rem_len = 2 + 2 + tlen + 1; /* packet ID + topic len + topic + qos */

    sub_pkt[0] = (MQTT_PKT_SUBSCRIBE << 4) | 2;
    int shlen = 1;
    shlen += encode_rem_len(&sub_pkt[shlen], sub_rem_len);
    sub_pkt[shlen++] = 0; sub_pkt[shlen++] = 1; /* Packet ID 1 */
    sub_pkt[shlen++] = (tlen >> 8) & 0xFF;
    sub_pkt[shlen++] = tlen & 0xFF;
    memcpy(&sub_pkt[shlen], topic, tlen);
    shlen += tlen;
    sub_pkt[shlen++] = 0; /* Requested QoS 0 */

    write(fd, sub_pkt, shlen);

    /* Read SUBACK */
    uint8_t suback[5];
    if (read(fd, suback, 5) < 5 || (suback[0] >> 4) != MQTT_PKT_SUBACK) {
        fprintf(stderr, "Error: MQTT subscribe failed\n");
        close(fd);
        return 1;
    }

    /* 3. Read loop */
    uint8_t rx_buf[4096];
    int rx_len = 0;
    int received_count = 0;

    struct pollfd pfd;
    pfd.fd = fd;
    pfd.events = POLLIN;

    while (running) {
        int ret = poll(&pfd, 1, 1000);
        if (ret < 0) break;
        if (ret == 0) continue;

        if (pfd.revents & POLLIN) {
            int n = read(fd, rx_buf + rx_len, sizeof(rx_buf) - rx_len);
            if (n <= 0) break;
            rx_len += n;

            while (rx_len >= 2) {
                uint8_t pkt_type = (rx_buf[0] >> 4) & 0x0F;
                int rem_len = 0;
                int rem_bytes = decode_rem_len(&rx_buf[1], rx_len - 1, &rem_len);
                if (rem_bytes < 0) break;

                int total = 1 + rem_bytes + rem_len;
                if (rx_len < total) break;

                if (pkt_type == MQTT_PKT_PUBLISH) {
                    const uint8_t *pl = &rx_buf[1 + rem_bytes];
                    int rtopic_len = (pl[0] << 8) | pl[1];
                    char rtopic[128] = {0};
                    int cpl = rtopic_len < 127 ? rtopic_len : 127;
                    memcpy(rtopic, &pl[2], cpl);

                    int ppos = 2 + rtopic_len;
                    int qos = (rx_buf[0] >> 1) & 0x03;
                    if (qos > 0) ppos += 2; /* skip packet id */

                    int payload_len = rem_len - ppos;
                    char rpayload[2048] = {0};
                    int cpy_len = payload_len < 2047 ? payload_len : 2047;
                    if (cpy_len > 0) memcpy(rpayload, &pl[ppos], cpy_len);

                    if (verbose) {
                        printf("%s: %s\n", rtopic, rpayload);
                    } else {
                        printf("%s\n", rpayload);
                    }
                    fflush(stdout);

                    received_count++;
                    if (max_count > 0 && received_count >= max_count) {
                        running = 0;
                        break;
                    }
                }

                int rem = rx_len - total;
                if (rem > 0) memmove(rx_buf, rx_buf + total, rem);
                rx_len = rem;
            }
        }
    }

    uint8_t disc[2] = { (MQTT_PKT_DISCONNECT << 4), 0 };
    write(fd, disc, 2);
    close(fd);
    return 0;
}
