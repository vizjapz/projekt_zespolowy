# Kubernetes Webhosting Cluster - Ansible Automation

Projekt uczelniony: **Projekt i wdrożenie środowiska webhostingowego opartego na Kubernetes**

Automatyzacja Ansible do postawienia 3-nodowego klastra Kubernetes na czystych maszynach wirtualnych z Ubuntu 22.04/24.04 LTS.

## Architektura

```
┌─────────────────────────────────────────────────────┐
│                   Ansible Controller                 │
│                 (laptop / VM zarządzająca)            │
└──────────┬──────────────┬──────────────┬────────────┘
           │              │              │
     ┌─────▼─────┐  ┌────▼──────┐  ┌───▼───────┐
     │  k8s-cp01  │  │  k8s-w01  │  │  k8s-w02  │
     │  master    │  │  worker   │  │  worker   │
     │ 10.10.10.11│  │10.10.10.12│  │10.10.10.13│
     │  8GB RAM   │  │  8GB RAM  │  │  8GB RAM  │
     │  2-4 vCPU  │  │  2-4 vCPU │  │  2-4 vCPU │
     └────────────┘  └───────────┘  └───────────┘
```

## Wymagania

### Maszyny docelowe (nody K8s)
- Ubuntu 22.04 LTS lub 24.04 LTS (minimal server)
- 8 GB RAM, 2-4 vCPU, 50+ GB dysk
- Łączność sieciowa między nodami
- Użytkownik z uprawnieniami sudo
- Klucz SSH skonfigurowany

### Maszyna zarządzająca (Ansible controller)
- Python 3.8+
- Ansible 2.15+
- `ansible-galaxy collection install community.general ansible.posix`

## Struktura projektu

```
k8s-ansible/
├── ansible.cfg                 # Konfiguracja Ansible
├── inventory/
│   └── hosts.yml               # Inwentarz - adresy nodów
├── group_vars/
│   ├── all.yml                 # Zmienne globalne
│   └── k8s_cluster.yml         # Zmienne klastra K8s
├── roles/
│   ├── common/                 # Hardening OS
│   │   ├── tasks/main.yml
│   │   ├── handlers/main.yml
│   │   ├── templates/
│   │   │   ├── sshd_config.j2
│   │   │   ├── 90-hardening.conf.j2
│   │   │   ├── jail.local.j2
│   │   │   ├── chrony.conf.j2
│   │   │   └── 50unattended-upgrades.j2
│   │   └── files/
│   │       └── ufw-before-rules-icmp.rules
│   ├── containerd/             # Container runtime
│   │   ├── tasks/main.yml
│   │   └── handlers/main.yml
│   ├── kubernetes-prereqs/     # Prereqs K8s
│   │   ├── tasks/main.yml
│   │   └── templates/
│   │       ├── k8s-modules.conf.j2
│   │       └── k8s-sysctl.conf.j2
│   ├── kubernetes-master/      # Control-plane init
│   │   ├── tasks/main.yml
│   │   └── templates/
│   │       └── kubeadm-config.yml.j2
│   └── kubernetes-worker/      # Worker join
│       └── tasks/main.yml
├── playbooks/
│   ├── site.yml                # Główny playbook (wszystko)
│   ├── 01-hardening.yml        # Tylko hardening
│   ├── 02-kubernetes.yml       # Tylko K8s
│   └── 99-reset.yml            # Reset klastra
└── README.md
```

## Szybki start

### 1. Skonfiguruj inwentarz

Edytuj `inventory/hosts.yml` — wpisz adresy IP swoich VM.

### 2. Wpisz swój klucz SSH

Edytuj `group_vars/all.yml` — zmień `ansible_user_ssh_pubkey`.

### 3. Przetestuj łączność

```bash
ansible all -m ping
```

### 4. Uruchom pełny deployment

```bash
# Wszystko po kolei
ansible-playbook playbooks/site.yml

# Lub etapami:
ansible-playbook playbooks/01-hardening.yml
ansible-playbook playbooks/02-kubernetes.yml
```

### 5. Zweryfikuj klaster

```bash
ssh ansible@10.10.10.11
kubectl get nodes -o wide
kubectl get pods -n kube-system
```

## Co robi każda rola

### `common` — Hardening OS
- Aktualizacja systemu i instalacja pakietów bazowych
- Konfiguracja użytkownika ansible z kluczem SSH
- Hardening SSH (wyłączenie root login, password auth, crypto hardening)
- Hardening kernela (sysctl - ochrona przed atakami sieciowymi)
- Firewall UFW (domyślnie deny incoming)
- Fail2ban (ochrona SSH)
- Chrony NTP (synchronizacja czasu)
- Automatyczne aktualizacje bezpieczeństwa (z blacklistą pakietów K8s)
- Auditd
- Banner logowania

### `containerd` — Container Runtime
- Instalacja containerd z oficjalnego repo Docker
- Konfiguracja SystemdCgroup = true
- Ustawienie pause image

### `kubernetes-prereqs` — Przygotowanie pod K8s
- Wyłączenie swap
- Moduły kernela (overlay, br_netfilter)
- Sysctl networking (ip_forward, bridge-nf-call)
- Repozytorium Kubernetes (pkgs.k8s.io)
- Instalacja kubeadm, kubelet, kubectl
- Apt hold na pakietach K8s
- Firewall — porty K8s (master/worker/Calico)
- crictl config
- kubectl bash completion + alias k

### `kubernetes-master` — Control-plane
- kubeadm init z dedykowanym ClusterConfiguration
- Konfiguracja kubectl (root + ansible)
- Instalacja Calico CNI
- Oczekiwanie na gotowość control-plane
- Generowanie join command dla workerów

### `kubernetes-worker` — Dołączenie workerów
- kubeadm join (token z mastera)
- Label node-role.kubernetes.io/worker

## Reset klastra

```bash
ansible-playbook playbooks/99-reset.yml
```

Wykonuje `kubeadm reset`, czyści iptables, interfejsy CNI i katalogi konfiguracyjne.

## Zmienne do dostosowania

| Zmienna | Domyślna wartość | Opis |
|---|---|---|
| `k8s_version` | `1.31` | Wersja Kubernetes |
| `k8s_pod_network_cidr` | `10.244.0.0/16` | CIDR sieci podów |
| `k8s_service_cidr` | `10.96.0.0/12` | CIDR sieci serwisów |
| `k8s_cni` | `calico` | Plugin CNI |
| `ssh_port` | `22` | Port SSH |
| `timezone` | `Europe/Warsaw` | Strefa czasowa |
| `ansible_user_ssh_pubkey` | — | Klucz publiczny SSH |

## Następne kroki (ArgoCD + WordPress)

Po uruchomieniu klastra, kolejne etapy projektu:
1. Instalacja MetalLB (LoadBalancer dla bare-metal)
2. Instalacja Ingress-NGINX
3. Instalacja cert-manager
4. Deployment ArgoCD
5. Konfiguracja GitLab repo z Helm charts
6. ArgoCD App of Apps → WordPress webhosting


