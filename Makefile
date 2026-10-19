CLANG = clang
CFLAGS = -O2 -g -Wall -target bpf -D__TARGET_ARCH_x86 -D__x86_64__ -I/usr/include/x86_64-linux-gnu

all: xdp_firewall.o

xdp_firewall.o: xdp_firewall.c
	$(CLANG) $(CFLAGS) -c $< -o $@

clean:
	rm -f xdp_firewall.o
