# Sing-box Egress Switch

一个运行在 Oracle Cloud ARM Ubuntu 实例上的 sing-box 出站 IP 切换工具。

它提供一个简单的 Web 管理页面，用来查看当前 `direct` 出站绑定 IP、候选 IP 列表，以及执行切换。切换完成后，页面会展示对应的公网 IPv4，并支持按顺序轮换到下一个 IP。

## 功能

- 展示当前 sing-box `direct` 出站绑定 IP
- 展示指定网卡上的候选 IPv4 列表
- 通过页面按钮切换到指定 IP
- 支持一键切换到下一个 IP
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

4. 启动服务

```bash
./scripts/start.sh
```

启动脚本会自动创建虚拟环境并安装依赖。

## 使用

启动后，可通过以下地址访问：

```text
http://<server-ip>:8080
```

如果你是通过当前 sing-box 代理访问这个页面，请确保你的访问来源公网 IP 与当前出口公网 IPv4 一致；本机 `127.0.0.1` 访问也始终放行。

页面支持两种切换方式：

- 点击右侧列表中的“切换到此地址”
- 点击左侧“切换到下一个 IP”

更新时间按 `UTC+8` 显示，格式为 `yyyy-MM-dd HH:mm:ss`。

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
