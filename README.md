# Zabbix Telegram Integration Role

Ansible role for deploying Zabbix-Telegram integration with interactive buttons on **RED OS 8/9**.

## 📋 Overview

This role deploys a complete Zabbix-Telegram integration solution that includes:

- ✅ Alert script for sending notifications from Zabbix to Telegram
- ✅ Interactive bot for handling callback buttons in notifications
- ✅ Graph image embedding in alerts with watermark support
- ✅ Secure credential management with Ansible Vault
- ✅ Systemd service for bot management with auto-restart
- ✅ SELinux policy support for enhanced security
- ✅ Proxy support for environments with restricted internet access

---

## ✨ Features

| Feature | Description |
|---------|------------|
| **Interactive Notifications** | Handle Zabbix events with inline buttons: Acknowledge, Comments, History, Last Value |
| **Graph Integration** | Automatic embedding of Zabbix graphs in problem notifications |
| **Watermark Support** | Add custom watermarks to graph images for internal use labeling |
| **Tag-based Mentions** | Mention users in Telegram based on Zabbix event tags |
| **Custom Settings via Tags** | Control notification behavior via `ZNTSettings:` tags (e.g., `graphs_period=3600`) |
| **Secure Design** | SELinux contexts, proper file permissions, Vault support for secrets |
| **Proxy Support** | Configurable HTTP/HTTPS/SOCKS proxy for Telegram API access |
| **Custom Telegram API Server** | Support for local Telegram Bot API proxy (`tg_server_api`) |
| **Isolated Python 3.13** | Automatic download and setup of standalone Python 3.13 (no system dependencies) |
| **Zabbix 7+ Compatible** | Patched `aiozabbix` for compatibility with Zabbix 7.0+ API changes |

---

## 📦 Requirements

| Component | Version | Notes |
|-----------|---------|-------|
| **Ansible** | ≥ 2.9 | Tested with 2.15+ |
| **Target OS** | RED OS 8, Ubuntu 22 | RHEL/Debian - compatible distributions  |
| **Zabbix Server** | ≥ 7.0 | Tested with 7.0 |
| **Python** | 3.13 (auto-installed) | Standalone build, no system Python required |
| **Telegram Bot** | Any | Token from [@BotFather](https://t.me/BotFather) |

### Network Requirements

- Outbound HTTPS access to `api.telegram.org` (or custom API server via example server https://tdlib.github.io/telegram-bot-api/ creds get in https://my.telegram.org/auth?to=apps)
- Access to Zabbix API endpoint (`https://zabbix.local/api_jsonrpc.php`)
- Optional: Proxy server for restricted environments

---

## ⚙️ Role Variables

### 🔧 Python & Virtual Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_venv_recreate` | `false` | If `true`, forces complete removal and recreation of venv |
| `python_standalone_url` | *(see vars)* | URL to download standalone Python 3.13 tarball |
| `python_install_base` | `"/opt"` | Base directory for standalone Python installation |
| `python_exec` | `"{{ python_install_base }}/python/bin/python3.13"` | Full path to Python 3.13 binary |

> 💡 **Note**: `python_standalone_url` is defined in `vars/main.yml`. Update it periodically to use the latest [python-build-standalone](https://github.com/astral-sh/python-build-standalone/releases) release.

### 📁 Paths and Files

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_alertscripts_dir` | `"/usr/lib/zabbix/alertscripts"` | Directory for Zabbix alert scripts |
| `zbxtelegram_script_name` | `"zbxTelegram.py"` | Main alert script filename |
| `zbxtelegram_bot_script_name` | `"zbxTelegramBot.py"` | Callback handler bot filename |
| `zbxtelegram_config_name` | `"zbxTelegram_config.py"` | Configuration file filename |
| `zbxtelegram_venv_dir` | `"{{ zbxtelegram_alertscripts_dir }}/venv"` | Virtual environment directory |
| `zbxtelegram_files_dir` | `"{{ zbxtelegram_alertscripts_dir }}/zbxTelegram_files"` | Directory for static files (fonts, test images) |
| `zbxtelegram_log_dir` | `"/var/log/zabbix/zbxtelegram"` | Directory for log files |
| `zbxtelegram_cache_dir` | `"/var/lib/zabbix/zbxtelegram"` | Directory for cache files (chat IDs) |

### 👤 User and Permissions

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_user` | `"zabbix"` | System user to run scripts and bot |
| `zbxtelegram_group` | `"zabbix"` | System group for file ownership |

### 🤖 Telegram Bot Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_bot_token` | `""` | **Required**: Telegram bot token from @BotFather |
| `zbxtelegram_proxy_enabled` | `false` | Enable proxy for Telegram API requests |
| `zbxtelegram_proxy_url` | `"http://proxy.local:3128"` | Proxy URL (HTTP/HTTPS/SOCKS) |
| `zbxtelegram_no_proxy` | `"localhost,127.0.0.1,.local,.localdomain"` | Comma-separated list of hosts to bypass proxy |
| `zbxtelegram_server_api` | `""` | Custom Telegram API server URL (e.g., local Bot API proxy). If empty, uses official `api.telegram.org` |

### 🔌 Zabbix API Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_zabbix_url` | `"https://zabbix.local/"` | Base URL of Zabbix web interface |
| `zbxtelegram_zabbix_user` | `"zbx_bot"` | Zabbix API user with read permissions |
| `zbxtelegram_zabbix_pass` | `""` | **Required**: Password for Zabbix API user |
| `zbxtelegram_ca_bundle` | `"/etc/pki/tls/certs/ca-bundle.crt"` | Path to CA bundle for SSL verification |
| `zbxtelegram_ssl_cert` | `"/etc/pki/tls/certs/ca-bundle.crt"` | Path to SSL certificate (if using client cert auth) |

### 🔔 Notification Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_keyboard_enabled` | `true` | Enable interactive inline keyboard in notifications |
| `zbxtelegram_watermark_enabled` | `true` | Add watermark to embedded graph images |
| `zbxtelegram_watermark_font` | `"{{ zbxtelegram_alertscripts_dir }}/zbxTelegram_files/OpenSans-Regular.ttf"` | Path to font file for watermark |
| `zbxtelegram_watermark_label` | `"Только для внутреннего использования"` | Text label for watermark |
| `zbxtelegram_watermark_minimal_height` | `200` | Minimum image height to apply watermark |
| `zbxtelegram_watermark_rotate` | `30` | Rotation angle for watermark text (degrees) |
| `zbxtelegram_watermark_fill` | `"white"` | Color for watermark text |
| `zbxtelegram_graph_period_default` | `10800` | Default graph time period in seconds (3 hours) |

### 🏷️ Tag-Based Features

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_tags` | `true` | Enable tag parsing in notifications |
| `zbxtelegram_tags_event` | `true` | Include `#{tag_value}` for event tags |
| `zbxtelegram_tags_eventid` | `true` | Include `#eid_{eventid}` tag |
| `zbxtelegram_tags_itemid` | `false` | Include `#iid_{itemid}` tag |
| `zbxtelegram_tags_triggerid` | `true` | Include `#tid_{triggerid}` tag |
| `zbxtelegram_tags_actionid` | `false` | Include `#aid_{actionid}` tag |
| `zbxtelegram_tags_hostid` | `true` | Include `#hid_{hostid}` tag |

### 🔐 SELinux Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_selinux_log_context` | `"var_log_t"` | SELinux context for log directory |
| `zbxtelegram_selinux_lib_context` | `"var_lib_t"` | SELinux context for cache directory |
| `zbxtelegram_selinux_alertscripts_context` | `"bin_t"` | SELinux context for executable scripts |

### ⚙️ Systemd Service

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_service_name` | `"zbxtelegrambot.service"` | Name of systemd service unit |
| `zbxtelegram_restart_sec` | `10` | Delay before auto-restart on failure |
| `zbxtelegram_env_file` | `"/etc/sysconfig/zbxtelegrambot"` | Path to environment file for service |

### 🔗 Zabbix Integration

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_zabbix_alertscript_name` | `"Telegram"` | Name of media type in Zabbix |
| `zbxtelegram_zabbix_media_type` | `"Telegram"` | Name of media type for user configuration |

### 🐛 Debug Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `zbxtelegram_debug_enabled` | `false` | Enable debug-level logging |

---

## 🔐 Security Considerations

### Credential Management

Store sensitive variables using **Ansible Vault**:

```bash
# Encrypt individual variables
ansible-vault encrypt_string '123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11' \
  --name 'zbxtelegram_bot_token'

ansible-vault encrypt_string 'MySecurePassword123' \
  --name 'zbxtelegram_zabbix_pass'
```

Use in playbook:
```yaml
vars:
  zbxtelegram_bot_token: !vault |
    $ANSIBLE_VAULT;1.1;AES256
    66386439653...
  zbxtelegram_zabbix_pass: !vault |
    $ANSIBLE_VAULT;1.1;AES256
    34316439653...
```

### SSL/TLS Certificates

- ✅ Use trusted CA-signed certificates for Zabbix API
- ✅ Configure `zbxtelegram_ca_bundle` with proper CA chain
- ⚠️ Self-signed certificates require `ssl._create_unverified_context` (enabled by role for internal use)
- 🔒 For production, prefer valid certificates over disabling verification

### File Permissions

| Path | Permissions | Owner | Purpose |
|------|------------|-------|---------|
| `{{ zbxtelegram_config_name }}` | `0640` | `zabbix:zabbix` | Configuration with secrets |
| `*.py` scripts | `0755` | `zabbix:zabbix` | Executable alert scripts |
| `{{ zbxtelegram_log_dir }}` | `0755` | `zabbix:zabbix` | Log files (`0644`) |
| `{{ zbxtelegram_cache_dir }}` | `0755` | `zabbix:zabbix` | Cache files (`0644`) |

### SELinux

The role automatically sets SELinux contexts:
```bash
# Applied contexts
semanage fcontext -a -t bin_t "{{ zbxtelegram_alertscripts_dir }}(/.*)?"
semanage fcontext -a -t var_log_t "{{ zbxtelegram_log_dir }}(/.*)?"
semanage fcontext -a -t var_lib_t "{{ zbxtelegram_cache_dir }}(/.*)?"
restorecon -Rv {{ zbxtelegram_alertscripts_dir }}
```

---

## 🚀 Installation

### 1. Prepare Telegram Bot

1. Start chat with [@BotFather](https://t.me/BotFather)
2. Send `/newbot` and follow instructions
3. Save the token: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
4. (Optional) Set bot description, about text, profile picture

### 2. Prepare Zabbix User

1. Create user `zbx_bot` in Zabbix with:
   - Type: **User**
   - Password: strong password
   - Role: **Guest** or custom role with **API read** permissions
2. Enable **API access** in user settings
3. (Optional) Add user to Telegram chat and note chat ID

### 3. Configure Playbook Variables

```yaml
# inventory/group_vars/zabbix_servers.yml
---
zbxtelegram_bot_token: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  66386439653...
zbxtelegram_zabbix_pass: !vault |
  $ANSIBLE_VAULT;1.1;AES256
  34316439653...

zbxtelegram_zabbix_url: "https://zabbix.example.com/"
zbxtelegram_zabbix_user: "zbx_telegram_bot"

# Optional: proxy for restricted networks
zbxtelegram_proxy_enabled: true
zbxtelegram_proxy_url: "http://proxy.example.com:3128"

# Optional: custom Telegram API server
# zbxtelegram_server_api: "http://local-telegram-api:8081"
```

### 4. Run the Playbook

```bash
# With vault password prompt
ansible-playbook -i inventory/ site.yml \
  --ask-vault-pass \
  --limit zabbix_servers

# Or with vault password file
ansible-playbook -i inventory/ site.yml \
  --vault-password-file ~/.vault_pass.txt \
  --limit zabbix_servers
```

### 5. Verify Deployment

```bash
# Check service status
systemctl status zbxtelegrambot.service

# View logs
journalctl -u zbxtelegrambot.service -f
tail -f /var/log/zabbix/zbxtelegram/znt.log

# Test bot response
# Send /start to your bot in Telegram
```

---

## ⚙️ Configuration

### Zabbix Media Type

The role cannot automatically create a media type. Manual configuration:

| Parameter | Value |
|-----------|-------|
| **Name** | `Telegram` |
| **Type** | `Script` |
| **Script name** | `zbxTelegram.py` |
| **Script parameters** | `{ALERT.SENDTO}`, `{ALERT.SUBJECT}`, `{ALERT.MESSAGE}` |
| **Enabled** | ✅ |

### Alert Script Parameters

The script expects exactly 3 parameters in order:

1. `username` — Telegram username (`@user`), chat ID (`-100123456789`), or group name
2. `subject` — Alert subject (supports emoji mapping via config)
3. `message` — Alert message in **XML format** (see template below)

### XML Message Template

```xml
<?xml version="1.0" encoding="UTF-8" ?>
<root>
  <body>
    <messages>
      <![CDATA[
Host: {HOST.HOST} [{HOST.IP}]
Last value: {ITEM.LASTVALUE1} ({TIME})
Duration: {EVENT.AGE}
Description: {EVENT.NAME}]]>
    </messages>
  </body>
  <settings>
    <!-- Feature toggles -->
    <graphs>True</graphs>
    <hostlinks>True</hostlinks>
    <graphlinks>True</graphlinks>
    <acklinks>True</acklinks>
    <eventlinks>True</eventlinks>
    <triggerlinks>True</triggerlinks>
    <eventtag>True</eventtag>
    <eventidtag>True</eventidtag>
    <itemidtag>True</itemidtag>
    <triggeridtag>True</triggeridtag>
    <actionidtag>True</actionidtag>
    <hostidtag>True</hostidtag>
    <zntsettingstag>True</zntsettingstag>
    <zntmentions>True</zntmentions>
    <keyboard>True</keyboard>

    <!-- Graph settings -->
    <graphs_period>7200</graphs_period>

    <!-- Context data -->
    <host>{HOST.HOST}</host>
    <itemid>{ITEM.ID1} {ITEM.ID2} {ITEM.ID3}</itemid>
    <triggerid>{TRIGGER.ID}</triggerid>
    <eventid>{EVENT.ID}</eventid>
    <actionid>{ACTION.ID}</actionid>
    <hostid>{HOST.ID}</hostid>
    <title><![CDATA[{HOST.HOST} - {EVENT.NAME}]]></title>
    <triggerurl><![CDATA[{TRIGGER.URL}]]></triggerurl>
    <eventtags><![CDATA[{EVENT.TAGS}]]></eventtags>
  </settings>
</root>
```

Or import `files/mediatypes.yaml`

### Tag-Based Features

#### Mentions
Add `mentions:@user1 @user2` to event tags to mention users in Telegram:
```
Event tags: severity:high,mentions:@admin @oncall
```
Result: `@admin @oncall` will be notified in Telegram.

#### Dynamic Settings
Use `ZNTSettings:` prefix to control notification behavior:
```
Event tags: ZNTSettings:no_graph,ZNTSettings:graphs_period=3600
```
- `no_graph` — skip graph attachment for this event
- `graphs_period=3600` — use 1-hour graph instead of default

---

## 🎮 Usage

### Sending Alerts

1. Configure **Action** in Zabbix:
   - Conditions: your trigger logic
   - Operations → Send message → Media type: `Telegram`
   - Send to: `user ID` or `-100123456789` (chat ID)

2. Test with a manual trigger or use the built-in test mode:
   ```bash
   # From Zabbix server
   sudo -u zabbix /usr/lib/zabbix/alertscripts/zbxTelegram.py \
     "user ID" \
     "Test subject" \
     "This is the test message from Zabbix" \

   ```

### Interactive Buttons

When `zbxtelegram_keyboard_enabled: true`, notifications include:

| Button | Action |
|--------|--------|
| 💬 | Show event comments/acknowledges history |
| ✅ | Acknowledge event with custom comment (3-min timeout) |
| 📈 | Show event history: status, timestamps, trigger info |
| ⏱ | Show last values of related items |

### Acknowledge Workflow

1. Click ✅ on notification
2. Bot prompts: *"Enter comment for event #12345"*
3. Type comment (min. 3 chars) within 3 minutes
4. Bot confirms and updates Zabbix with:
   ```
   {your comment}

   Acknowledged via Telegram by John Doe (@johndoe)
   ```
5. Original notification updates: ✅ button removed, confirmation text added

---

## 🐛 Troubleshooting

### Common Issues

| Symptom | Possible Cause | Solution |
|---------|---------------|----------|
| Bot doesn't respond | Wrong token, bot not started | Verify token, send `/start` to bot |
| "Chat not found" | Bot not added to group/chat | Add bot to chat, grant admin rights if needed |
| Graphs not attached | Zabbix API auth failed | Check `zbxtelegram_zabbix_user/pass`, API permissions |
| SSL certificate errors | Self-signed cert, missing CA | Set `zbxtelegram_ca_bundle` or ensure role's SSL bypass is active |
| Permission denied | Wrong file ownership/SELinux | Run `restorecon -Rv`, check `ls -lZ` |
| Proxy connection failed | Wrong proxy URL, auth required | Verify `zbxtelegram_proxy_url`, use `http://user:pass@proxy:port` |

### Log Files

```bash
# Alert script logs
tail -f /var/log/zabbix/zbxtelegram/znt.log

# Bot service logs
journalctl -u zbxtelegrambot.service -f

# Debug mode: enable in config
zbxtelegram_debug_enabled: true
```

### Debug Checklist

```bash
# 1. Verify Python version in venv
/usr/lib/zabbix/alertscripts/venv/bin/python --version
# Expected: Python 3.13.x

# 2. Test Zabbix API connection
curl -k -X POST https://zabbix.local/api_jsonrpc.php \
  -H "Content-Type: application/json-rpc" \
  -d '{"jsonrpc":"2.0","method":"user.login","params":{"username":"zbx_bot","password":"..."},"id":1}'

# 3. Test Telegram API (with custom server if configured)
/usr/lib/zabbix/alertscripts/venv/bin/python -c "
import asyncio
from aiogram import Bot
async def test():
    bot = Bot(token='YOUR_TOKEN')
    me = await bot.get_me()
    print(f'Bot: @{me.username}')
asyncio.run(test())
"

# 4. Check SELinux denials
ausearch -m avc -ts recent | grep zbxtelegram
```

### Reinstall venv (if dependencies break)

```yaml
# Run with force recreate flag
ansible-playbook site.yml \
  -e zbxtelegram_venv_recreate=true \
  --tags "install,venv"
```

---

## 📦 Dependencies

The role automatically installs required system packages:

```yaml
# RED OS / RHEL packages
- python3
- python3-pip
- python3-devel
- libjpeg-turbo-devel
- zlib-devel
- gcc
- libffi-devel
- openssl-devel
- policycoreutils-python-utils  # for SELinux management
```

> 💡 Standalone Python 3.13 is downloaded and installed to `/opt/python/`, so system Python version doesn't matter.

---

## 🔄 Upgrading

### Update Python Standalone

1. Check latest release: https://github.com/astral-sh/python-build-standalone/releases
2. Update `vars/main.yml`:
   ```yaml
   python_standalone_url: "https://github.com/astral-sh/python-build-standalone/releases/download/YYYYMMDD/cpython-3.13.X+YYYYMMDD-...tar.gz"
   ```
3. Recreate venv:
   ```bash
   ansible-playbook site.yml -e zbxtelegram_venv_recreate=true --tags "install,venv"
   ```

### Update Python Dependencies

1. Edit `requirements.txt` in role files
2. Recreate venv or run:
   ```bash
   source /usr/lib/zabbix/alertscripts/venv/bin/activate
   pip install -r /usr/lib/zabbix/alertscripts/requirements.txt --upgrade
   ```

### Update Role Code

```bash
# If using git for role management
cd /etc/ansible/roles/zbxtelegram
git pull origin main

# Re-deploy
ansible-playbook site.yml --tags "deploy"
```

---

## 📄 License

MIT License — see [LICENSE](LICENSE) file for details.

---

## 👤 Author Information

This role was created for **RTK-INFORM** by **Sergey Sadovnikov**.

- 📧 Contact: @sersad
- 🏢 Organization: RTK-INFORM
- 🗓️ Last updated: April 2026

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Commit changes: `git commit -m 'Add amazing feature'`
4. Push to branch: `git push origin feature/amazing-feature`
5. Open Pull Request

### Development Notes

- Test changes in isolated environment first
- Ensure SELinux policies are updated if adding new file paths
- Update `defaults/main.yml` for any new variables
- Document breaking changes in release notes

---

> ⚠️ **Disclaimer**: This role is designed for internal use in RTK infrastructure. Adapt security settings (SSL, permissions, SELinux) to your organization's policies before production deployment.
