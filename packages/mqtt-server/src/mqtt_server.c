/*
 * mqtt_server.c - Lightweight MQTT 3.1.1 Broker for ESP32-S3 Linux
 *
 * Implements core MQTT 3.1.1 broker protocol:
 * CONNECT, CONNACK, PUBLISH, PUBACK, SUBSCRIBE, SUBACK, PINGREQ, PINGRESP, DISCONNECT
 * Wildcard subscription matching: '+' (single-level) and '#' (multi-level).
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <signal.h>
#include <fcntl.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <poll.h>
#include <time.h>

#define DEFAULT_PORT 1883
#define MAX_CLIENTS 32
#define MAX_TOPICS_PER_CLIENT 16
#define BUFFER_SIZE 4096
#define MAX_TOPIC_LEN 128
#define MAX_CLIENT_ID_LEN 64

/* MQTT Packet Types */
#define MQTT_PKT_CONNECT     1
#define MQTT_PKT_CONNACK     2
#define MQTT_PKT_PUBLISH     3
#define MQTT_PKT_PUBACK      4
#define MQTT_PKT_SUBSCRIBE   8
#define MQTT_PKT_SUBACK      9
#define MQTT_PKT_UNSUBSCRIBE 10
#define MQTT_PKT_UNSUBACK    11
#define MQTT_PKT_PINGREQ     12
#define MQTT_PKT_PINGRESP    13
#define MQTT_PKT_DISCONNECT  14

typedef struct {
    char topic[MAX_TOPIC_LEN];
    int qos;
} Subscription;

typedef struct {
    int fd;
    char client_id[MAX_CLIENT_ID_LEN];
    Subscription subs[MAX_TOPICS_PER_CLIENT];
    int num_subs;
    uint8_t rx_buf[BUFFER_SIZE];
    int rx_len;
    time_t last_active;
    int keep_alive;
    int is_active;
} Client;

static Client clients[MAX_CLIENTS];
static int running = 1;
static int verbose = 0;

static void handle_signal(int sig) {
    (void)sig;
    running = 0;
}

static void log_msg(const char *tag, const char *msg) {
    time_t now = time(NULL);
    struct tm *tm_info = localtime(&now);
    char tbuf[26];
    strftime(tbuf, 26, "%Y-%m-%d %H:%M:%S", tm_info);
    printf("[%s] [%s] %s\n", tbuf, tag, msg);
    fflush(stdout);
}

/* Set non-blocking socket */
static int set_nonblocking(int fd) {
    int flags = fcntl(fd, F_GETFL, 0);
    if (flags == -1) return -1;
    return fcntl(fd, F_SETFL, flags | O_NONBLOCK);
}

/* Match MQTT topic against subscription pattern with + and # */
static int topic_matches(const char *sub, const char *topic) {
    while (*sub && *topic) {
        if (*sub == '#') {
            return 1; /* # matches everything remaining */
        }
        if (*sub == '+') {
            /* Skip until next / or end */
            while (*topic && *topic != '/') topic++;
            sub++;
            continue;
        }
        if (*sub != *topic) {
            return 0;
        }
        sub++;
        topic++;
    }
    if (*sub == '#' || (*sub == '\0' && *topic == '\0')) {
        return 1;
    }
    return 0;
}

/* Variable-length integer encoder */
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

/* Variable-length integer decoder */
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
    return -1; /* incomplete or overflow */
}

/* Send a raw buffer to a client */
static int client_send(Client *c, const uint8_t *data, int len) {
    if (c->fd < 0 || !c->is_active) return -1;
    int total = 0;
    while (total < len) {
        int n = write(c->fd, data + total, len - total);
        if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) continue;
            return -1;
        }
        total += n;
    }
    return total;
}

/* Forward publish packet to subscribed clients */
static void broadcast_publish(const char *topic, const uint8_t *payload, int payload_len, int qos, int sender_fd) {
    uint8_t header[16];
    int topic_len = strlen(topic);
    int rem_len = 2 + topic_len + (qos > 0 ? 2 : 0) + payload_len;

    header[0] = (MQTT_PKT_PUBLISH << 4) | (qos > 0 ? 2 : 0);
    int hlen = 1;
    hlen += encode_rem_len(&header[hlen], rem_len);

    header[hlen++] = (topic_len >> 8) & 0xFF;
    header[hlen++] = topic_len & 0xFF;

    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (!clients[i].is_active || clients[i].fd < 0) continue;
        int matched = 0;
        for (int s = 0; s < clients[i].num_subs; s++) {
            if (topic_matches(clients[i].subs[s].topic, topic)) {
                matched = 1;
                break;
            }
        }
        if (matched) {
            client_send(&clients[i], header, hlen);
            client_send(&clients[i], (const uint8_t *)topic, topic_len);
            if (qos > 0) {
                uint8_t pkt_id[2] = {0, 1};
                client_send(&clients[i], pkt_id, 2);
            }
            if (payload_len > 0) {
                client_send(&clients[i], payload, payload_len);
            }
        }
    }
}

/* Close and reset a client */
static void disconnect_client(Client *c) {
    if (c->is_active) {
        if (verbose) {
            char buf[128];
            snprintf(buf, sizeof(buf), "Client disconnected: %s (fd %d)", c->client_id, c->fd);
            log_msg("BROKER", buf);
        }
        close(c->fd);
        c->fd = -1;
        c->is_active = 0;
        c->rx_len = 0;
        c->num_subs = 0;
        c->client_id[0] = '\0';
    }
}

/* Process single MQTT packet */
static int handle_packet(Client *c, uint8_t pkt_type, const uint8_t *payload, int len) {
    c->last_active = time(NULL);

    switch (pkt_type) {
        case MQTT_PKT_CONNECT: {
            if (len < 10) return -1;
            /* Read client ID */
            int pos = 10;
            if (pos + 2 > len) return -1;
            int cid_len = (payload[pos] << 8) | payload[pos + 1];
            pos += 2;
            if (pos + cid_len > len) return -1;
            if (cid_len >= MAX_CLIENT_ID_LEN) cid_len = MAX_CLIENT_ID_LEN - 1;
            memcpy(c->client_id, &payload[pos], cid_len);
            c->client_id[cid_len] = '\0';

            /* Send CONNACK (accepted, code 0) */
            uint8_t connack[4] = { (MQTT_PKT_CONNACK << 4), 2, 0, 0 };
            client_send(c, connack, 4);

            if (verbose) {
                char buf[128];
                snprintf(buf, sizeof(buf), "Client connected: %s (fd %d)", c->client_id, c->fd);
                log_msg("BROKER", buf);
            }
            return 0;
        }

        case MQTT_PKT_PUBLISH: {
            if (len < 2) return -1;
            int topic_len = (payload[0] << 8) | payload[1];
            if (2 + topic_len > len) return -1;

            char topic[MAX_TOPIC_LEN];
            int cp_len = topic_len < MAX_TOPIC_LEN - 1 ? topic_len : MAX_TOPIC_LEN - 1;
            memcpy(topic, &payload[2], cp_len);
            topic[cp_len] = '\0';

            int ppos = 2 + topic_len;
            int packet_id = 0;
            int qos = (c->rx_buf[0] >> 1) & 0x03;
            if (qos > 0) {
                if (ppos + 2 > len) return -1;
                packet_id = (payload[ppos] << 8) | payload[ppos + 1];
                ppos += 2;
            }

            const uint8_t *p_data = &payload[ppos];
            int p_len = len - ppos;

            if (verbose) {
                char buf[256];
                snprintf(buf, sizeof(buf), "PUBLISH '%s' (%d bytes) from %s", topic, p_len, c->client_id);
                log_msg("BROKER", buf);
            }

            broadcast_publish(topic, p_data, p_len, qos, c->fd);

            if (qos == 1) {
                uint8_t puback[4] = { (MQTT_PKT_PUBACK << 4), 2, (uint8_t)(packet_id >> 8), (uint8_t)(packet_id & 0xFF) };
                client_send(c, puback, 4);
            }
            return 0;
        }

        case MQTT_PKT_SUBSCRIBE: {
            if (len < 2) return -1;
            int packet_id = (payload[0] << 8) | payload[1];
            int pos = 2;

            while (pos + 2 < len) {
                int tlen = (payload[pos] << 8) | payload[pos + 1];
                pos += 2;
                if (pos + tlen > len) break;
                if (c->num_subs < MAX_TOPICS_PER_CLIENT) {
                    int cp = tlen < MAX_TOPIC_LEN - 1 ? tlen : MAX_TOPIC_LEN - 1;
                    memcpy(c->subs[c->num_subs].topic, &payload[pos], cp);
                    c->subs[c->num_subs].topic[cp] = '\0';
                    pos += tlen;
                    int sub_qos = (pos < len) ? payload[pos++] : 0;
                    c->subs[c->num_subs].qos = sub_qos;
                    c->num_subs++;

                    if (verbose) {
                        char buf[256];
                        snprintf(buf, sizeof(buf), "SUBSCRIBE '%s' by %s", c->subs[c->num_subs - 1].topic, c->client_id);
                        log_msg("BROKER", buf);
                    }
                } else {
                    pos += tlen + 1;
                }
            }

            /* Send SUBACK (QoS 0 granted) */
            uint8_t suback[5] = { (MQTT_PKT_SUBACK << 4), 3, (uint8_t)(packet_id >> 8), (uint8_t)(packet_id & 0xFF), 0 };
            client_send(c, suback, 5);
            return 0;
        }

        case MQTT_PKT_UNSUBSCRIBE: {
            if (len < 2) return -1;
            int packet_id = (payload[0] << 8) | payload[1];
            int pos = 2;
            while (pos + 2 < len) {
                int tlen = (payload[pos] << 8) | payload[pos + 1];
                pos += 2;
                if (pos + tlen > len) break;
                char utopic[MAX_TOPIC_LEN];
                int cp = tlen < MAX_TOPIC_LEN - 1 ? tlen : MAX_TOPIC_LEN - 1;
                memcpy(utopic, &payload[pos], cp);
                utopic[cp] = '\0';
                pos += tlen;

                for (int s = 0; s < c->num_subs; s++) {
                    if (strcmp(c->subs[s].topic, utopic) == 0) {
                        c->subs[s] = c->subs[c->num_subs - 1];
                        c->num_subs--;
                        break;
                    }
                }
            }
            uint8_t unsuback[4] = { (MQTT_PKT_UNSUBACK << 4), 2, (uint8_t)(packet_id >> 8), (uint8_t)(packet_id & 0xFF) };
            client_send(c, unsuback, 4);
            return 0;
        }

        case MQTT_PKT_PINGREQ: {
            uint8_t pingresp[2] = { (MQTT_PKT_PINGRESP << 4), 0 };
            client_send(c, pingresp, 2);
            return 0;
        }

        case MQTT_PKT_DISCONNECT: {
            disconnect_client(c);
            return 0;
        }

        default:
            return 0;
    }
}

/* Parse buffer for client */
static void process_client_data(Client *c) {
    while (c->rx_len >= 2) {
        uint8_t pkt_type = (c->rx_buf[0] >> 4) & 0x0F;
        int rem_len = 0;
        int rem_len_bytes = decode_rem_len(&c->rx_buf[1], c->rx_len - 1, &rem_len);
        if (rem_len_bytes < 0) return; /* need more bytes for length */

        int total_len = 1 + rem_len_bytes + rem_len;
        if (c->rx_len < total_len) return; /* need full packet */

        const uint8_t *payload = &c->rx_buf[1 + rem_len_bytes];
        handle_packet(c, pkt_type, payload, rem_len);

        /* Shift buffer */
        int remain = c->rx_len - total_len;
        if (remain > 0) {
            memmove(c->rx_buf, c->rx_buf + total_len, remain);
        }
        c->rx_len = remain;
    }
}

int main(int argc, char **argv) {
    int port = DEFAULT_PORT;
    const char *bind_ip = "0.0.0.0";
    int daemonize = 0;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-p") == 0 && i + 1 < argc) {
            port = atoi(argv[++i]);
        } else if (strcmp(argv[i], "-b") == 0 && i + 1 < argc) {
            bind_ip = argv[++i];
        } else if (strcmp(argv[i], "-v") == 0) {
            verbose = 1;
        } else if (strcmp(argv[i], "-d") == 0) {
            daemonize = 1;
        } else if (strcmp(argv[i], "-h") == 0 || strcmp(argv[i], "--help") == 0) {
            printf("Usage: mqtt-server [-p port] [-b bind_ip] [-v] [-d]\n");
            printf("  -p <port>     Port to listen on (default 1883)\n");
            printf("  -b <ip>       IP to bind to (default 0.0.0.0)\n");
            printf("  -v            Verbose logging\n");
            printf("  -d            Run in background as daemon\n");
            return 0;
        }
    }

    if (daemonize) {
        if (daemon(0, 0) < 0) {
            perror("daemon");
            return 1;
        }
    }

    signal(SIGTERM, handle_signal);
    signal(SIGINT, handle_signal);
    signal(SIGPIPE, SIG_IGN);

    int listen_fd = socket(AF_INET, SOCK_STREAM, 0);
    if (listen_fd < 0) {
        perror("socket");
        return 1;
    }

    int opt = 1;
    setsockopt(listen_fd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
    set_nonblocking(listen_fd);

    struct sockaddr_in addr;
    memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    inet_pton(AF_INET, bind_ip, &addr.sin_addr);

    if (bind(listen_fd, (struct sockaddr *)&addr, sizeof(addr)) < 0) {
        perror("bind");
        close(listen_fd);
        return 1;
    }

    if (listen(listen_fd, 10) < 0) {
        perror("listen");
        close(listen_fd);
        return 1;
    }

    char start_msg[128];
    snprintf(start_msg, sizeof(start_msg), "Broker listening on %s:%d (MQTT 3.1.1)", bind_ip, port);
    log_msg("INIT", start_msg);

    struct pollfd pfd[MAX_CLIENTS + 1];

    while (running) {
        pfd[0].fd = listen_fd;
        pfd[0].events = POLLIN;
        pfd[0].revents = 0;

        int num_poll = 1;
        int client_idx_map[MAX_CLIENTS + 1];

        for (int i = 0; i < MAX_CLIENTS; i++) {
            if (clients[i].is_active && clients[i].fd >= 0) {
                pfd[num_poll].fd = clients[i].fd;
                pfd[num_poll].events = POLLIN;
                pfd[num_poll].revents = 0;
                client_idx_map[num_poll] = i;
                num_poll++;
            }
        }

        int ret = poll(pfd, num_poll, 1000);
        if (ret < 0) {
            if (errno == EINTR) continue;
            perror("poll");
            break;
        }

        /* Check new connections */
        if (pfd[0].revents & POLLIN) {
            struct sockaddr_in caddr;
            socklen_t clen = sizeof(caddr);
            int cfd = accept(listen_fd, (struct sockaddr *)&caddr, &clen);
            if (cfd >= 0) {
                set_nonblocking(cfd);
                int slot = -1;
                for (int i = 0; i < MAX_CLIENTS; i++) {
                    if (!clients[i].is_active) {
                        slot = i;
                        break;
                    }
                }
                if (slot >= 0) {
                    clients[slot].fd = cfd;
                    clients[slot].is_active = 1;
                    clients[slot].rx_len = 0;
                    clients[slot].num_subs = 0;
                    clients[slot].last_active = time(NULL);
                    snprintf(clients[slot].client_id, sizeof(clients[slot].client_id), "client-%d", cfd);
                } else {
                    close(cfd); /* Max clients reached */
                }
            }
        }

        /* Check client sockets */
        for (int p = 1; p < num_poll; p++) {
            int ci = client_idx_map[p];
            if (pfd[p].revents & (POLLERR | POLLHUP | POLLNVAL)) {
                disconnect_client(&clients[ci]);
                continue;
            }
            if (pfd[p].revents & POLLIN) {
                int space = BUFFER_SIZE - clients[ci].rx_len;
                if (space > 0) {
                    int n = read(clients[ci].fd, clients[ci].rx_buf + clients[ci].rx_len, space);
                    if (n > 0) {
                        clients[ci].rx_len += n;
                        process_client_data(&clients[ci]);
                    } else if (n == 0 || (n < 0 && errno != EAGAIN && errno != EWOULDBLOCK)) {
                        disconnect_client(&clients[ci]);
                    }
                }
            }
        }
    }

    log_msg("SHUTDOWN", "Stopping MQTT Broker...");
    for (int i = 0; i < MAX_CLIENTS; i++) {
        if (clients[i].is_active) disconnect_client(&clients[i]);
    }
    close(listen_fd);
    return 0;
}
