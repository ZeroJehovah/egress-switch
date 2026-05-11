# Sing-box Egress Switch

一个运行在 Oracle Cloud ARM Ubuntu 实例上的 sing-box 出站 IP 切换工具。

它提供一个简单的 Web 管理页面，用来查看当前 `direct` 出站绑定 IP、候选 IP 列表、各 IP 最近使用起止时间，以及执行切换。切换完成后，页面会展示对应的公网 IPv4，并支持优先切换到最长未使用的 IP。

## 功能

- 展示当前 sing-box `direct` 出站绑定 IP
- 展示指定网卡上的候选 IPv4 列表
- 展示每个候选 IP 的最近使用起止时间，并按使用终止时间以 1 天、3 天、7 天、7 天外四档颜色区分；右侧列表不展示状态列，主要 IP 以整行渐变底色轻量高亮
- 通过页面按钮切换到指定 IP
- 支持一键切换到最长未使用的 IP
- 切换后刷新并缓存当前出口公网 IPv4
- 提供 `switch-next-ip.py` 供 `crontab` 调用
- 对页面、静态资源和 AJAX 接口启用来源 IP 白名单

当前白名单规则：

- 放行 `127.0.0.1`
- 放行当前出站 IP 对应的公网 IPv4

## 运行前提

- Ubuntu 环境
- 已安装 `python3`，建议同时安装 `python3-venv`
- 已安装并配置好 `sing-box`
- 目标网卡上已经绑定多个可切换 IPv4
- `sing-box` 配置中存在 `tag=direct` 的 outbound，并使用 `inet4_bind_address`

## 部署

1. 克隆仓库

```bash
git clone <your-repo-url>
cd egress-switch
```

2. 准备配置文件

```bash
cp .env.example .env
```

3. 按实际环境修改 `.env`

常用配置项：

- `SINGBOX_CONFIG_PATH`：sing-box 配置文件路径
- `SINGBOX_SERVICE_NAME`：systemd 服务名，默认 `sing-box`
- `SWITCH_IP_INTERFACE`：需要读取候选 IP 的网卡名
- `SWITCH_IP_SUBNET_PREFIX`：候选 IP 过滤前缀，例如 `10.0.0`
- `SWITCH_IP_PORT`：Web 页面监听端口，默认 `8080`
- `SWITCH_IP_PRIMARY_IP`：当前实例的主要 IP，会在右侧 IP 列表中以整行渐变底色轻量高亮，默认 `10.0.0.18`
- `SWITCH_IP_USAGE_HISTORY_PATH`：使用时间记录文件，默认 `.run/ip-usage-history.txt`
- `SWITCH_IP_SYSTEMD_SERVICE_NAME`：Web 服务对应的 systemd 单元名，默认 `switch-ip`；留空可禁用脚本中的 systemd 检测

4. 启动服务

```bash
./scripts/start.sh
```

启动脚本会自动创建虚拟环境并安装依赖。

## 开机自启动

推荐使用 `systemd` 托管现有脚本。

1. 创建服务文件

```bash
sudo nano /etc/systemd/system/switch-ip.service
```

将下面内容写入服务文件，并把 `/path/to/egress-switch` 替换为你的实际部署目录：

```ini
[Unit]
Description=Sing-box Egress Switch
After=network-online.target sing-box.service
Wants=network-online.target

[Service]
Type=forking
User=root
WorkingDirectory=/path/to/egress-switch
PIDFile=/path/to/egress-switch/.run/switch-ip.pid
ExecStart=/path/to/egress-switch/scripts/start.sh
ExecStop=/path/to/egress-switch/scripts/stop.sh
ExecReload=/path/to/egress-switch/scripts/restart.sh
Restart=on-failure
RestartSec=3
TimeoutStartSec=120
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
```

说明：

- 这里使用 `Type=forking`，因为 `scripts/start.sh` 会在后台启动 Web 进程并写入 PID 文件。
- 这里使用 `User=root`，因为切换功能需要修改 sing-box 配置并重启 `sing-box` 服务。

2. 重新加载 `systemd` 并设置开机启动

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now switch-ip
```

3. 查看运行状态

```bash
sudo systemctl status switch-ip
sudo journalctl -u switch-ip -f
```

4. 常用管理命令

```bash
sudo systemctl restart switch-ip
sudo systemctl stop switch-ip
sudo systemctl start switch-ip
sudo systemctl disable switch-ip
```

## 使用

启动后，可通过以下地址访问：

```text
http://<server-ip>:8080
```

如果你是通过当前 sing-box 代理访问这个页面，请确保你的访问来源公网 IP 与当前出口公网 IPv4 一致；本机 `127.0.0.1` 访问也始终放行。

页面支持两种切换方式：

- 点击右侧列表中的“切换到此地址”
- 点击左侧“切换到下一个 IP”，实际会优先选择从未使用过的地址；若没有未使用地址，则选择使用终止时间最早的地址

候选 IP 的使用时间按 `UTC+8` 显示，格式为 `yyyy-MM-dd HH:mm:ss`。时间列展示“开始时间 - 结束时间”；当前使用中的地址展示为“开始时间 - 当前使用中”，并使用默认中性色。时间列保留分层配色，颜色按使用终止时间判断，越近越接近橙色，越远越接近绿色；右侧列表不再展示状态列或等级标签。

## 常用命令

启动：

```bash
./scripts/start.sh
```

重启：

```bash
./scripts/restart.sh
```

停止：

```bash
./scripts/stop.sh
```

更新代码并重启：

```bash
./scripts/update.sh
```

如果当前 Web 服务已经由 `systemd` 托管，`start.sh`、`stop.sh`、`restart.sh`、`update.sh` 会优先调用对应的 `systemctl` 命令，避免再次手动拉起一份进程导致端口冲突。非 root 用户执行这些脚本时，会自动尝试 `sudo -n systemctl ...`，因此请确保当前账号具备免密 sudo 权限。

手动切换到指定 IP：

```bash
python3 scripts/switch-egress-ip.py 10.0.0.145
```

切换到下一个 IP：

```bash
python3 scripts/switch-next-ip.py
```

示例 `crontab`：

```cron
*/10 * * * * cd /path/to/egress-switch && /usr/bin/python3 scripts/switch-next-ip.py >> /tmp/switch-next-ip.log 2>&1
```

## 开源许可

本项目使用 `MIT License`，详见 [LICENSE](./LICENSE)。
