#include <linux/bpf.h>
#include <bpf/bpf_helpers.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/tcp.h>
#include <arpa/inet.h>

#define MAX_REQUESTS 60
#define TIME_WINDOW_NS 10000000000ULL // 10 segundos en nanosegundos

struct ip_stats {
    __u64 last_seen;
    __u32 count;
};

struct {
    __uint(type, BPF_MAP_TYPE_LRU_HASH);
    __type(key, __u32);
    __type(value, struct ip_stats);
    __uint(max_entries, 10000);
} ip_tracker SEC(".maps");

SEC("xdp")
int xdp_firewall(struct xdp_md *ctx) {
    void *data = (void *)(long)ctx->data;
    void *data_end = (void *)(long)ctx->data_end;
    
    // 1. Validar cabecera Ethernet e IP
    struct ethhdr *eth = data;
    if ((void *)(eth + 1) > data_end) return XDP_PASS;
    if (eth->h_proto != htons(ETH_P_IP)) return XDP_PASS;

    struct iphdr *ip = (void *)(eth + 1);
    if ((void *)(ip + 1) > data_end) return XDP_PASS;
    if (ip->protocol != IPPROTO_TCP) return XDP_PASS;

    // 2. Validar cabecera TCP
    struct tcphdr *tcp = (void *)(ip + 1);
    if ((void *)(tcp + 1) > data_end) return XDP_PASS;

    // 3. Obtener IP de origen
    __u32 src_ip = ip->saddr;
    __u64 now = bpf_ktime_get_ns();
    
    // 4. Buscar IP en el mapa
    struct ip_stats *stats = bpf_map_lookup_elem(&ip_tracker, &src_ip);
    if (stats) {
        // Si el último paquete fue hace más de 10s, reiniciar el contador
        if (now - stats->last_seen > TIME_WINDOW_NS) {
            stats->count = 1;
            stats->last_seen = now;
        } else {
            stats->count++;
            // Si excede el umbral, DROP!
            if (stats->count > MAX_REQUESTS) {
                return XDP_DROP;
            }
        }
    } else {
        // Primera vez que vemos esta IP
        struct ip_stats new_stats = { .last_seen = now, .count = 1 };
        bpf_map_update_elem(&ip_tracker, &src_ip, &new_stats, BPF_ANY);
    }

    return XDP_PASS;
}

char _license[] SEC("license") = "GPL";
