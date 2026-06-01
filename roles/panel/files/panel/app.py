import os
import re
import secrets
import subprocess
from flask import Flask, render_template, request, redirect, url_for, session, flash
from jinja2 import Environment, FileSystemLoader

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))

ADMIN_PASSWORD = os.environ.get('PANEL_PASSWORD', 'admin123')
LETSENCRYPT_EMAIL = os.environ.get('LETSENCRYPT_EMAIL', 'admin@example.com')
K8S_TEMPLATES = '/opt/panel/k8s'
KUBECONFIG = '/etc/rancher/k3s/k3s.yaml'


def kubectl(args, stdin=None):
    result = subprocess.run(
        f'k3s kubectl {args}',
        shell=True, capture_output=True, text=True,
        input=stdin, env={**os.environ, 'KUBECONFIG': KUBECONFIG}
    )
    return result


def sanitize_ns(domain):
    s = re.sub(r'[^a-z0-9]', '-', domain.lower()).strip('-')
    return f'wp-{s}'


@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    r = kubectl('get ns --no-headers -o custom-columns=NAME:.metadata.name')
    namespaces = [n.strip() for n in r.stdout.splitlines() if n.strip().startswith('wp-')]

    instances = []
    for ns in namespaces:
        domain = ns[3:].replace('-', '.')

        r_pod = kubectl(f'get pods -n {ns} -l app=wordpress --no-headers 2>/dev/null')
        pod_status = 'Pending'
        if r_pod.stdout.strip():
            cols = r_pod.stdout.strip().split()
            pod_status = cols[2] if len(cols) >= 3 else 'Unknown'

        r_cert = kubectl(f'get certificate -n {ns} --no-headers 2>/dev/null')
        cert_ready = 'True' in r_cert.stdout

        instances.append({
            'domain': domain,
            'ns': ns,
            'pod_status': pod_status,
            'cert_ready': cert_ready,
        })

    return render_template('index.html', instances=instances)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        flash('Nieprawidłowe hasło', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/deploy', methods=['POST'])
def deploy():
    if not session.get('logged_in'):
        return redirect(url_for('login'))

    domain = request.form.get('domain', '').strip().lower()
    php_version = request.form.get('php_version', '8.3')

    if not re.match(r'^[a-z0-9][a-z0-9.-]+\.[a-z]{2,}$', domain):
        flash(f'Nieprawidłowa domena: {domain}', 'danger')
        return redirect(url_for('index'))

    if php_version not in ('8.2', '8.3', '8.4'):
        flash('Nieprawidłowa wersja PHP', 'danger')
        return redirect(url_for('index'))

    ns = sanitize_ns(domain)
    db_password = secrets.token_urlsafe(16)
    db_root_password = secrets.token_urlsafe(16)

    jenv = Environment(loader=FileSystemLoader(K8S_TEMPLATES))
    manifest = jenv.get_template('wordpress.yaml.j2').render(
        domain=domain,
        ns=ns,
        php_version=php_version,
        db_password=db_password,
        db_root_password=db_root_password,
    )

    result = kubectl('apply -f -', stdin=manifest)
    if result.returncode != 0:
        flash(f'Błąd deployu: {result.stderr[:400]}', 'danger')
    else:
        flash(
            f'WordPress dla {domain} jest wdrażany. '
            'Certyfikat pojawi się po wskazaniu domeny na IP serwera i propagacji DNS.',
            'success'
        )

    return redirect(url_for('index'))


@app.route('/delete/<ns>', methods=['POST'])
def delete(ns):
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    if not re.match(r'^wp-[a-z0-9-]+$', ns):
        flash('Nieprawidłowa operacja', 'danger')
        return redirect(url_for('index'))
    kubectl(f'delete namespace {ns}')
    flash(f'Instancja {ns} usunięta', 'success')
    return redirect(url_for('index'))


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
