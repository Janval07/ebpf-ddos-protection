# Mitigación de DDoS con eBPF/XDP vs Fail2Ban

Este repositorio contiene el código y el análisis de la práctica de mitigación de ataques DDoS utilizando eBPF (a través del hook XDP) comparado con la solución tradicional de Fail2Ban.

## 1. Objetivo
Demostrar las ventajas de eBPF/XDP sobre Fail2Ban en la protección de servicios HTTP (Nginx en Docker) contra ataques de denegación de servicio. Mientras Fail2Ban analiza logs en el espacio de usuario, eBPF actúa directamente en el kernel, descartando paquetes antes de que consuman recursos del servidor.

## 2. Arquitectura del Experimento
*   **Servicios protegidos:** Dashboard en Docker (Frontend Nginx en el puerto 8090).
*   **Entorno de ataque:** El script `flood.py` se ejecuta desde una máquina Windows externa, atacando a la IP de la máquina virtual Ubuntu (`172.18.86.178`). Se hace desde fuera para que el tráfico realmente pase por la interfaz de red (`eth0`) y no por el loopback local.
*   **Umbral de tolerancia:** 60 peticiones por IP en una ventana de 10 segundos (misma configuración para ambos sistemas).

## 3. Implementación de eBPF (`xdp_firewall.c`)
El programa en C utiliza un mapa `BPF_MAP_TYPE_LRU_HASH` para llevar el conteo de peticiones por IP (`ip_tracker`). 
*   Si una IP supera las 60 peticiones en menos de 10 segundos (usando `bpf_ktime_get_ns()`), el programa retorna `XDP_DROP`.
*   Esto indica al kernel que destruya el paquete en la capa de driver de la tarjeta de red, sin asignar memoria (`sk_buff`) y sin que Nginx se entere del ataque.

## 4. Resultados Comparativos

### A. Prueba con Fail2Ban
*   **Ejecución:** Se lanzó un ataque de 20 peticiones/segundo durante 15 segundos (300 peticiones totales).
*   **Resultado:** Nginx procesó las primeras 69 peticiones. Fail2Ban leyó los logs, detectó el patrón, y aplicó una regla en `iptables` bloqueando la IP. El script terminó con un **52% de peticiones fallidas**.
*   **Impacto:** El servidor web tuvo que procesar y escribir en el disco (logs) todas las peticiones hasta que la regla de firewall se activó.

### B. Prueba con eBPF (XDP)
*   **Ejecución:** Mismo ataque (300 peticiones en 15s) desde la máquina Windows.
*   **Resultado:** Las primeras 60 peticiones pasaron. En la petición 61, el kernel destruyó el paquete. El script terminó con un **74% de peticiones fallidas** (solo 24 peticiones exitosas).
*   **Impacto:** Nginx dejó de recibir tráfico de golpe. Los logs del contenedor se detuvieron en seco. El servidor no sufrió desgaste de CPU ni de I/O procesando el ataque.

## 5. Conclusión
*   **Fail2Ban** es útil como primera línea de defensa, pero es reactivo y depende del sistema de archivos (logs). En ataques volumétricos, el servidor puede caerse antes de que Fail2Ban aplique la regla.
*   **eBPF/XDP** es proactivo y altamente eficiente. Bloquea el ataque a nivel de red, garantizando que los recursos del servidor web se mantengan intactos y disponibles para usuarios legítimos.

## 6. Instrucciones de Ejecución
1. Compilar el programa: `make`
2. Cargar eBPF en la red: `sudo ip link set dev eth0 xdp obj xdp_firewall.o sec xdp`
3. Lanzar el ataque desde la máquina externa: `python flood.py <IP_VM> 8090 --duration 15 --concurrency 10 --rps 20`
4. (Opcional) Verificar logs de Nginx detenidos: `docker logs -f dashboard-frontend`
5. Remover eBPF al terminar: `sudo ip link set dev eth0 xdp off`