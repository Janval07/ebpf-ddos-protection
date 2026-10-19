# Mitigación de DDoS con eBPF/XDP vs Fail2Ban

## 1. Objetivo
Demostrar que eBPF/XDP ofrece una mitigación de ataques DDoS más eficiente que Fail2Ban, actuando directamente en el kernel (capa de red) en lugar de en el espacio de usuario (capa de aplicación).

## 2. Arquitectura
- **Servicios protegidos:** Dashboard en Docker (Frontend Nginx, Backend FastAPI, LDAP).
- **Fail2Ban:** Analiza los logs de Nginx y aplica reglas de iptables.
- **eBPF/XDP:** Programa en C (`xdp_firewall.c`) cargado en la interfaz `eth0` que cuenta paquetes TCP SYN por IP y descarta (`XDP_DROP`) si exceden el umbral (60 peticiones / 10 segundos).

## 3. Metodología de Pruebas
Se utilizó el script `flood.py` (modificado en la práctica anterior) ejecutándolo desde una máquina externa (Windows) hacia la IP de la VM (172.18.86.178) en el puerto 8090.
- **Ataque:** 20 peticiones por segundo durante 15 segundos (300 peticiones totales).

## 4. Resultados

### A. Con Fail2Ban
- **Comportamiento:** Las peticiones se procesaron hasta alcanzar el umbral. Fail2Ban leyó los logs, detectó la IP y aplicó la regla en iptables.
- **Resultado:** 69 peticiones exitosas antes del bloqueo. El servidor Nginx procesó y registró todo el tráfico hasta el baneo.
- **CPU:** Aumento temporal debido al parseo de logs de Nginx.

### B. Con eBPF/XDP
- **Comportamiento:** El kernel interceptó los paquetes en la tarjeta de red. Al superar el umbral, descartó el tráfico sin llegar a Docker.
- **Resultado:** Solo 24 peticiones exitosas. El 74% de las peticiones fueron bloqueadas a nivel de kernel.
- **CPU:** Prácticamente sin impacto. Nginx no procesó los paquetes maliciosos.

## 5. Conclusión
eBPF/XDP demostró ser superior para ataques volumétricos. Mientras que Fail2Ban deja que el servidor web procese las peticiones maliciosas hasta que se activa el baneo (lo que consume recursos y llena los logs), eBPF descarta los paquetes en la capa más temprana posible del kernel, protegiendo el servicio y manteniendo el rendimiento del sistema.

## 6. Cómo reproducir
1. Compilar el programa: `make`
2. Cargar en la interfaz: `sudo ip link set dev eth0 xdp obj xdp_firewall.o sec xdp`
3. Atacar desde otra máquina: `python flood.py <IP_VM> 8090 --duration 15 --concurrency 10 --rps 20`
4. Quitar eBPF: `sudo ip link set dev eth0 xdp off`