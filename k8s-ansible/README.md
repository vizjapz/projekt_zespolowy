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