# k8s-wordpress

## Project Overview

Ansible project that bootstraps a 3-node k3s cluster (1 control plane + 2 workers) on Ubuntu 22.04. Test environment for WordPress deployment. Uses air-gap installation (no internet required on target nodes). k3s ships with Traefik (ingress + Let's Encrypt TLS), CoreDNS, local-path-provisioner (PVCs), and metrics-server — no additional CNI or certbot needed.

## First-Time Setup

```bash
# 1. Download k3s binaries locally (requires internet on THIS machine, ~270MB)
./download-k3s.sh

# 2. Deploy cluster
ansible-playbook site.yml

# Dry run
ansible-playbook site.yml --check --diff

# Limit to specific hosts
ansible-playbook site.yml --limit control_plane
ansible-playbook site.yml --limit workers
```

Edit `inventory/hosts` to set correct node IPs before running.

## Key Variables

`group_vars/all.yml`:

| Variable | Effect |
|---|---|
| `k3s_server_ip` | Derived from inventory — IP of the control plane node |
| `k3s_server_url` | Agent join URL (`https://<cp_ip>:6443`) |

## Architecture — Play Execution Order

`site.yml` runs 4 sequential plays:

```
common      → all nodes     : swap off, nfs-common, /etc/hosts entries
k3s_server  → master only   : copies binary + airgap images, runs install.sh,
                              reads node token, stores as hostvars fact
k3s_agent   → workers       : copies binary + airgap images, runs install.sh agent
                              with K3S_URL + K3S_TOKEN from hostvars
verify      → master only   : waits for all nodes Ready + kube-system pods Running,
                              prints kubectl get nodes/pods
```

## Air-Gap Installation

`download-k3s.sh` fetches three files into `files/`:
- `k3s` — single binary (replaces kubeadm + kubelet + kubectl + containerd)
- `k3s-airgap-images-amd64.tar.zst` — all required images pre-bundled
- `install.sh` — official k3s install script from get.k3s.io

k3s auto-loads any `.tar.zst` from `/var/lib/rancher/k3s/agent/images/` on first start — no manual `ctr images import` needed.

## Idempotency Guards

- `k3s_server` install — skipped if `/etc/systemd/system/k3s.service` exists
- `k3s_agent` install — skipped if `/etc/systemd/system/k3s-agent.service` exists

## Join Command Flow

The join token is read from `/var/lib/rancher/k3s/server/node-token` on the master and stored as an in-memory hostvars fact (`k3s_node_token`). The `k3s_agent` role reads it via `hostvars[groups['control_plane'][0]]['k3s_node_token']`. Both plays must run in the same execution — running the agent play standalone will fail.

## kubectl Access

On the master node, use `k3s kubectl` or set:
```bash
export KUBECONFIG=/etc/rancher/k3s/k3s.yaml
kubectl get nodes
```

## WordPress Deployment

k3s ships with everything needed for WordPress out of the box:
- **Traefik** — ingress controller with built-in Let's Encrypt (no certbot)
- **local-path-provisioner** — automatic PersistentVolumes for DB storage
- **CoreDNS** — internal DNS for service discovery
