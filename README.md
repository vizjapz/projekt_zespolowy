# k8s-wordpress

Projekt uczelniony: **Wdrożenie środowiska webhostingowego opartego na Kubernetes (k3s)**

Automatyzacja Ansible stawiająca 3-nodowy klaster k3s na czystych maszynach Ubuntu 22.04/24.04.
Środowisko docelowe: deploy aplikacji WordPress z bazą MySQL, Traefik ingress i TLS.

---

## Topologia

```
                    ┌─────────────────────────────────┐
                    │        Ansible Controller        │
                    │    (laptop / maszyna lokalna)    │
                    │                                  │
                    │  ansible-playbook site.yml       │
                    └──────┬──────────┬───────────┬───┘
                    SSH    │          │           │
                    klucz  │          │           │
                    k8s_key│          │           │
                           │          │           │
          ┌────────────────▼──┐  ┌────▼──────┐  ┌▼──────────┐
          │    k8s-cp1        │  │  k8s-w01  │  │  k8s-w02  │
          │  control-plane    │  │  worker   │  │  worker   │
          │   10.4.0.50       │  │ 10.4.0.51 │  │ 10.4.0.52 │
          │                   │  │           │  │           │
          │  k3s server       │  │ k3s agent │  │ k3s agent │
          │  etcd (embedded)  │  │           │  │           │
          │  CoreDNS          │  │           │  │           │
          │  Traefik          │  │           │  │           │
          │  local-path-prov. │  │           │  │           │
          │  metrics-server   │  │           │  │           │
          └───────────────────┘  └───────────┘  └───────────┘
```

### Sieć klastra

| Sieć | CIDR | Opis |
|------|------|------|
| Węzły (fizyczna) | `10.4.0.0/24` | Sieć VM — komunikacja Ansible i k3s |
| Pody (k3s flannel) | `10.42.0.0/16` | Sieć wewnętrzna podów |
| Serwisy (ClusterIP) | `10.43.0.0/16` | Sieć wewnętrzna serwisów |

### Porty wymagane między węzłami

| Port | Protokół | Kierunek | Opis |
|------|----------|----------|------|
| `6443` | TCP | worker → master | k3s API server |
| `8472` | UDP | wszystkie | Flannel VXLAN (sieć podów) |
| `10250` | TCP | master → worker | kubelet metrics |
| `30443` | TCP | zewnątrz → master | Kubernetes Dashboard (NodePort) |
| `80 / 443` | TCP | zewnątrz → all | Traefik HTTP/HTTPS |

---

## Wymagania

### Maszyny docelowe
- Ubuntu 22.04 LTS lub 24.04 LTS (minimal server)
- min. 2 GB RAM, 2 vCPU, 20 GB dysk
- Dostęp SSH jako `root` (lub użytkownik z `sudo`)
- Łączność sieciowa między węzłami

### Maszyna zarządzająca (Ansible controller)
- Python 3.8+
- Ansible 2.14+
- `curl` (do `download-k3s.sh`)

---

## Struktura projektu

```
k8s-ansible/
│
├── site.yml                         # główny playbook — 4 sequential plays
├── dashboard.yml                    # osobny playbook — Kubernetes Dashboard (opcjonalny)
├── download-k3s.sh                  # pobiera k3s binary + airgap images lokalnie (~310 MB)
│
├── inventory/
│   └── hosts                        # INI: grupy control_plane / workers / k8s_cluster:children
│
├── group_vars/
│   └── all.yml                      # k3s_server_ip (z inventory), k3s_server_url (https://CP:6443)
│
├── files/
│   └── .gitkeep                     # placeholder — download-k3s.sh wrzuca tu pliki (nie w repo)
│
└── roles/
    │
    ├── common/
    │   └── tasks/
    │       └── main.yml             # apt update, curl+nfs-common, swapoff + fstab, /etc/hosts
    │
    ├── k3s_server/
    │   └── tasks/
    │       └── main.yml             # curl install.sh → k3s server, czeka na node-token,
    │                                # slurp tokenu → set_fact k3s_node_token, czeka na Ready
    │
    ├── k3s_agent/
    │   └── tasks/
    │       └── main.yml             # curl install.sh agent z K3S_URL + K3S_TOKEN (z hostvars mastera)
    │
    ├── verify/
    │   └── tasks/
    │       └── main.yml             # czeka aż 3/3 węzłów Ready, czeka na pody kube-system Running,
    │                                # wyświetla kubectl get nodes -o wide + pods -A
    │
    └── dashboard/
        ├── tasks/
        │   └── main.yml             # kubectl apply recommended.yaml (v2.7.0), ServiceAccount admin,
        │                            # NodePort 30443, slurp tokenu → debug URL + token
        └── files/
            └── dashboard-admin.yml  # manifesty: ServiceAccount, ClusterRoleBinding (cluster-admin),
                                     # Secret (service-account-token), Service NodePort 30443
```

---

## Kolejność wykonania playbooków

### `site.yml` — 4 plays

```
Play 1: common       → k8s_cluster (wszystkie 3 nody)
        ├─ apt update + instalacja curl, nfs-common
        ├─ swapoff -a + wykomentowanie swap w /etc/fstab
        └─ wpisy w /etc/hosts (k8s-master, k8s-worker1, k8s-worker2)

Play 2: k3s_server   → control_plane (10.4.0.50)
        ├─ curl -sfL https://get.k3s.io | sh -
        ├─ wait_for: /var/lib/rancher/k3s/server/node-token
        ├─ slurp tokenu → set_fact k3s_node_token
        └─ wait: node Ready (retry 20x co 10s)

Play 3: k3s_agent    → workers (10.4.0.51, 10.4.0.52)
        ├─ curl install.sh z K3S_URL + K3S_TOKEN z hostvars[master]
        └─ systemd: k3s-agent started + enabled

Play 4: verify       → control_plane
        ├─ wait: 3/3 węzłów Ready (retry 30x co 10s)
        ├─ debug: kubectl get nodes -o wide
        ├─ wait: pody kube-system Running
        └─ debug: kubectl get pods -A + podsumowanie
```

### `dashboard.yml` — osobny playbook

```
Play 1: dashboard    → control_plane
        ├─ kubectl apply dashboard v2.7.0 (namespace kubernetes-dashboard)
        ├─ wait: pod dashboard Running
        ├─ kubectl apply dashboard-admin.yml
        │    ├─ ServiceAccount: admin-user
        │    ├─ ClusterRoleBinding: admin-user → cluster-admin
        │    ├─ Secret: admin-user-token (service-account-token)
        │    └─ Service: NodePort 30443 → dashboard:8443
        └─ debug: URL (https://10.4.0.50:30443) + token logowania
```

---

## Szybki start

### 1. Skonfiguruj inventory

```ini
# inventory/hosts
[control_plane]
k8s-master ansible_host=10.4.0.50

[workers]
k8s-worker1 ansible_host=10.4.0.51
k8s-worker2 ansible_host=10.4.0.52
```

### 2. Wgraj klucz SSH na serwery

```bash
# Wygeneruj klucz (jeśli nie masz)
ssh-keygen -t ed25519 -f k8s_key -N ""

# Wgraj na każdy węzeł
for NODE in 10.4.0.50 10.4.0.51 10.4.0.52; do
  ssh-copy-id -i k8s_key.pub root@$NODE
done
```

### 3. Sprawdź połączenie

```bash
ansible all -m ping
```

### 4. Uruchom klaster

```bash
ansible-playbook site.yml
```

### 5. (Opcjonalnie) Kubernetes Dashboard

```bash
ansible-playbook dashboard.yml
# Otwórz: https://10.4.0.50:30443
```

---

## Zmienne (`group_vars/all.yml`)

| Zmienna | Wartość | Opis |
|---------|---------|------|
| `k3s_server_ip` | `{{ hostvars[groups['control_plane'][0]]['ansible_host'] }}` | IP mastera — pobierane z inventory |
| `k3s_server_url` | `https://{{ k3s_server_ip }}:6443` | URL dla agentów do dołączenia |

---

## Idempotentność

Każdy destruktywny krok jest zabezpieczony:

| Krok | Guard |
|------|-------|
| Instalacja k3s server | `creates: /etc/systemd/system/k3s.service` |
| Instalacja k3s agent | `creates: /etc/systemd/system/k3s-agent.service` |
| Wyłączenie swap w fstab | `replace` — idempotentny (komentuje tylko aktywne wpisy) |

Ponowne uruchomienie `ansible-playbook site.yml` na działającym klastrze jest bezpieczne.

---

## Dostęp do klastra

```bash
# Na masterze
k3s kubectl get nodes -o wide
k3s kubectl get pods -A

# Lokalnie (po skopiowaniu kubeconfig)
scp -i k8s_key root@10.4.0.50:/etc/rancher/k3s/k3s.yaml ~/.kube/config
sed -i 's/127.0.0.1/10.4.0.50/' ~/.kube/config
kubectl get nodes
```

---

## Trwałość danych

### Gdzie przechowywane są dane instancji WordPress

Każda instancja WordPress składa się z dwóch warstw danych, obie trwałe i odporne na restarty:

**1. Stan klastra — etcd**

Kubernetes przechowuje pełen stan wszystkich obiektów (Namespace, Deployment, Service, Ingress, Secret, PVC, certyfikaty TLS) w wbudowanej bazie etcd na węźle master. Dane te są zapisywane na dysku i przeżywają restart k3s oraz restart maszyny. Po ponownym uruchomieniu klastra wszystkie instancje WordPress wracają automatycznie do stanu sprzed zatrzymania.

**2. Pliki i baza danych — PersistentVolume**

Dane aplikacji (pliki WordPress, motywy, wtyczki, przesłane media) oraz zawartość bazy MySQL są przechowywane w PersistentVolumes zarządzanych przez `local-path-provisioner`. Fizyczna lokalizacja na węźle:

```
/var/lib/rancher/k3s/storage/
```

Wolumeny nie są usuwane przy restarcie podów ani węzłów — Kubernetes montuje je ponownie przy każdym uruchomieniu kontenera. Dane przeżywają również aktualizację obrazu Docker (np. zmianę wersji PHP) ponieważ wolumin jest przyłączany niezależnie od cyklu życia kontenera.

**3. Panel administracyjny — bezstanowy**

Panel WordPress (`wp-panel`) nie posiada własnej bazy danych. Lista aktywnych instancji jest odczytywana na żywo z API Kubernetes przy każdym załadowaniu strony. Restart usługi `wp-panel` lub restart węzła master nie powoduje utraty żadnych danych — panel po prostu ponownie odpytuje klaster i wyświetla aktualny stan.

### Cykl życia danych

| Zdarzenie | Skutek dla danych |
|-----------|-------------------|
| Restart poda WordPress / MySQL | Dane zachowane — wolumin montowany ponownie |
| Restart węzła k3s | Dane zachowane — pody startują automatycznie |
| Restart całego klastra | Dane zachowane — etcd i wolumeny na dysku |
| Usunięcie instancji przez panel | Dane **usuwane** — `kubectl delete namespace` usuwa PVC i wolumeny |

---

## Co daje k3s out-of-the-box

| Komponent | Opis |
|-----------|------|
| **containerd** | Container runtime (wbudowany w binarce k3s) |
| **Flannel** | CNI — sieć podów (VXLAN, CIDR 10.42.0.0/16) |
| **CoreDNS** | DNS wewnętrzny klastra |
| **Traefik** | Ingress controller + automatyczny TLS (Let's Encrypt) |
| **local-path-provisioner** | Automatyczne PersistentVolumes na dysku lokalnym |
| **metrics-server** | `kubectl top nodes/pods` |
| **etcd** | Wbudowana baza stanu klastra |

---

## Panele administracyjne

| Panel | Adres | Dane logowania |
|-------|-------|----------------|
| **WordPress Panel** — deploy nowych instancji WordPress | `http://10.4.0.50:5000` | hasło z `group_vars/all.yml` → `panel_password` |
| **Kubernetes Dashboard** — podgląd klastra (pody, namespace, logi) | `https://10.4.0.50:30443` | token z `dashboard-token.txt` (generowany przez `dashboard.yml`) |

### WordPress Panel

Prosty panel webowy do zarządzania instancjami WordPress na klastrze:
- Logowanie hasłem (ustawiane w `group_vars/all.yml` → `panel_password`)
- Formularz: domena + wersja PHP (8.2 / 8.3 / 8.4)
- Automatyczny deploy: Namespace, MySQL, WordPress, Ingress
- Automatyczny certyfikat TLS Let's Encrypt (HTTP-01 challenge przez Traefik)
- Lista aktywnych instancji z statusem podów i certyfikatów
- Usuwanie instancji wraz z danymi

```bash
# Deploy panelu
ansible-playbook panel.yml

# Zmiana hasła — edytuj group_vars/all.yml, następnie
ansible-playbook panel.yml
```

### Kubernetes Dashboard

Graficzny interfejs do podglądu stanu klastra (pody, namespace, logi, zasoby).

```bash
# Deploy dashboardu
ansible-playbook dashboard.yml
# Otwórz: https://10.4.0.50:30443
# Token zapisany w: dashboard-token.txt
```

