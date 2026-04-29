# Zabbix Telegram Integration Role

Ansible role for deploying Zabbix-Telegram integration with interactive buttons on RED OS.

## Overview

This role deploys a complete Zabbix-Telegram integration solution that includes:
- Alert script for sending notifications from Zabbix to Telegram
- Interactive bot for handling callback buttons in notifications
- Graph image embedding in alerts
- Secure credential management
- Systemd service for bot management

## Features

- **Interactive Notifications**: Handle Zabbix events with inline buttons (Acknowledge, Comments, History, etc.)
- **Graph Integration**: Automatic graph embedding in problem notifications
- **Watermark Support**: Add watermarks to graph images
- **Tag-based Mentions**: Mention users based on event tags
- **Secure Design**: SELinux support and proper file permissions
- **Proxy Support**: Configurable proxy for Telegram API access
- **Zabbix API Integration**: Direct integration with Zabbix for enhanced functionality

## Requirements

- Ansible 2.9 or higher
- RED OS 8 or 9
- Zabbix Server 5.0 or higher
- Telegram Bot Token (from @BotFather)
- Python 3.6 or higher

## Role Variables

### Paths and Files
```yaml
zbxtelegram_alertscripts_dir: "/usr/lib/zabbix/alertscripts"
zbxtelegram_script_name: "zbxTelegram.py"
zbxtelegram_bot_script_name: "zbxTelegramBot.py"
zbxtelegram_config_name: "zbxTelegram_config.py"
zbxtelegram_venv_dir: "{{ zbxtelegram_alertscripts_dir }}/venv"
zbxtelegram_files_dir: "{{ zbxtelegram_alertscripts_dir }}/zbxTelegram_files"
zbxtelegram_log_dir: "/var/log/zabbix/zbxtelegram"
zbxtelegram_cache_dir: "/var/lib/zabbix/zbxtelegram"
```

### User and Permissions
```yaml
zbxtelegram_user: "zabbix"
zbxtelegram_group: "zabbix"
```

### Telegram Bot Configuration
```yaml
zbxtelegram_bot_token: ""  # Required: your bot token
zbxtelegram_proxy_enabled: false
zbxtelegram_proxy_url: "http://proxy.local:3128"
zbxtelegram_no_proxy: localhost,127.0.0.1,.local,.localdomain
```

### Zabbix API Configuration
```yaml
zbxtelegram_zabbix_url: "https://zabbix.local/"
zbxtelegram_zabbix_user: "zbx_bot"
zbxtelegram_zabbix_pass: ""  # Required: bot user password
```

### Notification Settings
```yaml
zbxtelegram_keyboard_enabled: true
zbxtelegram_watermark_enabled: true
zbxtelegram_watermark_font: "{{ zbxtelegram_alertscripts_dir }}/zbxTelegram_files/OpenSans-Regular.ttf"
zbxtelegram_watermark_label: "Только для внутреннего использования"
zbxtelegram_graph_period_default: 10800  # 3 hours
```

### SELinux Configuration
```yaml
zbxtelegram_selinux_log_context: "var_log_t"
zbxtelegram_selinux_lib_context: "var_lib_t"
zbxtelegram_selinux_alertscripts_context: "bin_t"
```

### Systemd Service
```yaml
zbxtelegram_service_name: "zbxtelegrambot.service"
zbxtelegram_restart_sec: 10
zbxtelegram_env_file: "/etc/sysconfig/zbxtelegrambot"
```

## Security Considerations

### Credential Management
Store sensitive variables using Ansible Vault:
```bash
ansible-vault encrypt_string 'your_bot_token' --name 'zbxtelegram_bot_token'
ansible-vault encrypt_string 'your_zabbix_password' --name 'zbxtelegram_zabbix_pass'
```

### SSL Certificates
Ensure proper SSL certificate validation by:
1. Using trusted certificates for Zabbix API
2. Configuring proper CA bundles
3. Avoiding global SSL verification disabling

### File Permissions
The role sets appropriate file permissions:
- Configuration files: 0640 (owner: zabbix, group: zabbix)
- Executable scripts: 0755 (owner: zabbix, group: zabbix)
- Log files: 0644 (owner: zabbix, group: zabbix)

## Installation

1. Create a Telegram bot with @BotFather and obtain the token
2. Create a Zabbix user with API access permissions
3. Configure role variables in your playbook
4. Run the playbook

### Example Playbook
```yaml
---
- name: Deploy Zabbix Telegram Integration
  hosts: zabbix_servers
  become: yes
  vars:
    zbxtelegram_bot_token: !vault |
      $ANSIBLE_VAULT;1.1;AES256
      66386439653...
    zbxtelegram_zabbix_pass: !vault |
      $ANSIBLE_VAULT;1.1;AES256
      34316439653...
    zbxtelegram_zabbix_url: "https://zabbix.example.com/"
    zbxtelegram_zabbix_user: "zbx_telegram_bot"
    zbxtelegram_zabbix_integration: true
  roles:
    - zbxtelegram
```

## Configuration

### Zabbix Media Type
The role can automatically create the required media type in Zabbix. The media type configuration includes:
- Script name: `zbxTelegram.py`
- Parameters: `{ALERT.SENDTO}`, `{ALERT.SUBJECT}`, `{ALERT.MESSAGE}`

### Alert Script Parameters
The alert script expects three parameters:
1. `username` - Telegram username or chat ID
2. `subject` - Alert subject
3. `message` - Alert message in XML format

### Message Format
The message should be in XML format with the following structure:
```xml
<?xml version="1.0" encoding="UTF-8" ?>
<root>
  <body>
    <messages>
      <![CDATA[
Host: {HOST.HOST} [{HOST.IP}]
Last value: {ITEM.LASTVALUE1} ({TIME})
Duration: {EVENT.AGE}]]>
    </messages>
  </body>
  <settings>
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
    <graphs_period>7200</graphs_period>
    <host>{HOST.HOST}</host>
    <itemid>{ITEM.ID1} {ITEM.ID2} {ITEM.ID3} {ITEM.ID4}</itemid>
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

## Usage

### Sending Alerts
Configure Zabbix actions to use the Telegram media type with:
- Send to: Telegram username or chat ID
- Subject: Alert subject (supports emoji mapping)
- Message: XML formatted message

### Interactive Buttons
The bot supports the following interactive buttons:
- 💬 Comments: Show event comments/acknowledges
- ✅ Acknowledge: Acknowledge event with comment
- 📈 History: Show event history and current status
- ⏱ Last Value: Show last values of related items

### Tag-based Features
- **Mentions**: Mention users based on event tags (tag: `mentions:username1 username2`)
- **Settings**: Control notification behavior with tags (tag: `ZNTSettings:no_graph`, `ZNTSettings:graphs_period=3600`)

## Troubleshooting

### Common Issues

1. **Bot not receiving messages**: Ensure the bot token is correct and the bot is added to the chat/group
2. **Graphs not showing**: Check Zabbix API credentials and permissions
3. **SSL errors**: Verify SSL certificates and CA bundle configuration
4. **Permission errors**: Check file permissions and SELinux contexts

### Log Files
- Main log: `/var/log/zabbix/zbxtelegram/znt.log`
- Service log: `journalctl -u zbxtelegrambot.service`

### Debug Mode
Enable debug mode by setting:
```yaml
zbxtelegram_debug_enabled: true
```

## Dependencies

- python3
- python3-pip
- python3-devel
- libjpeg-turbo-devel
- zlib-devel
- gcc
- libffi-devel
- openssl-devel
- policycoreutils-python-utils (for SELinux)

## License

MIT

## Author Information

This role was created for RTK by Sergey Sadovnikov.