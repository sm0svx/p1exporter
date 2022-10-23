from machine import Pin, UART, I2C, WDT
import network
import socket
import time
import select
from metric import Metric
import re
#import config
import ubinascii
import sys
import json
import uos

# Configuration variable definitions
# These definitions are mainly used to build the HTML configuration form and
# handle the submit action.
CONFIG_VARS = [
    {
        'name': 'enable_oled',
        'type': 'checkbox',
        'text': 'Enable OLED',
        'default': False,
    },
    {
        'name': 'enable_wdt',
        'type': 'checkbox',
        'text': 'Enable Watchdog Timer',
        'default': True,
    },
    {
        'name': 'uart_no',
        'type': 'radio',
        'default': 1,
        'selections': [
            {
                'id': 'uart0',
                'text': 'UART 0',
                'value': '0',
            },
            {
                'id': 'uart1',
                'text': 'UART 1',
                'value': '1',
            },
        ],
    },
    {
        'name': 'uart_tx_gpio',
        'type': 'number',
        'text': 'UART TX GPIO Pin',
        'min': 1,
        'max': 40,
        'default': 4,
    },
    {
        'name': 'uart_rx_gpio',
        'type': 'number',
        'text': 'UART RX GPIO Pin',
        'min': 1,
        'max': 40,
        'default': 5,
    },
    {
        'name': 'uart_baudrate',
        'type': 'number',
        'text': 'UART Baudrate',
        'min': 300,
        'max': 115200,
        'default': 115200,
    },
    {
        'name': 'uart_bits',
        'type': 'radio',
        'default': 8,
        'selections': [
            {
                'id': 'uart_bits7',
                'text': 'UART 7 Bits',
                'value': '7',
            },
            {
                'id': 'uart_bits8',
                'text': 'UART 8 Bits',
                'value': '8',
            },
        ],
    },
    {
        'name': 'tz_offset',
        'type': 'number',
        'text': 'Timezone Offset Seconds',
        'min': -43200,
        'max': 43200,
        'default': 3600,
    },
    {
        'name': 'ap',
        'type': 'checkbox',
        'text': 'WiFi Access Point Mode',
        'default': True,
    },
    {
        'name': 'ssid',
        'type': 'text',
        'text': 'WiFi SSID',
        'default': 'p1exporter',
    },
    {
        'name': 'password',
        'type': 'password',
        'text': 'WiFi Password',
        'default': 'p1exporter',
    },
]

CONFIG_FILENAME = 'config.json'

starttime = time.ticks_ms()

if time.gmtime(0)[0] != 1970:
    raise Exception("Epoch year is not 1970!")

class DummyWDT:
    def feed(self):
        #print('Feed Watchdog')
        pass

wdt = DummyWDT()

def reboot():
    global wdt
    if type(wdt) == DummyWDT:
        wdt = WDT(timeout=1000)
    while True:
        time.sleep(1)
    
def save_config():
    with open(CONFIG_FILENAME, 'w') as f:
        json.dump(config, f)

def set_default_config():
    global config
    print('Writing default config file')
    config = dict()
    for var in CONFIG_VARS:
        config[var['name']] = var['default']
    save_config()

if CONFIG_FILENAME in uos.listdir('/'):
    with open(CONFIG_FILENAME, 'r') as f:
        config = json.load(f)
else:
    set_default_config()
    
print('Config:', config)

if config['enable_oled']:
    from ssd1306 import SSD1306_I2C
    i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400000)
    oled = SSD1306_I2C(128, 64, i2c)
    oled.text("P1 Exporter", 0, 0)
    oled.text("WiFi connect...", 0, 16)
    oled.show()

led = Pin('LED', Pin.OUT)
led.off()

if config['enable_wdt']:
    for i in range(0,10):
        time.sleep(1)
        led.toggle()
    print('Enabling Watchdog Timer')
    wdt = WDT(timeout=5000)
else:
    for i in range(0,4):
        time.sleep(1)
        led.toggle()
    
led.off()

sensor_temp = machine.ADC(4)
conversion_factor = 3.3 / (65535)
 
def wlan_setup_ap():
    global wlan
    try:
        ssid = config['ssid']
        password = config['password']
        if len(ssid) == 0:
            ssid = 'p1exporter'
            password = 'p1exporter'
        wlan = network.WLAN(network.AP_IF)
        wlan.config(essid=ssid, password=password)
        wlan.active(True)
    
        while not wlan.active():
            wdt.feed()
            time.sleep(1)

        print('Access point active')
        ip, netmask, gateway, dns = wlan.ifconfig()
        print("IP:", ip)
        print("netmask:", netmask)
        print("gateway:", gateway)
        print("dns:", dns)
        print("essid:", wlan.config('essid'))
        print("channel:", wlan.config('channel'))
    except Exception as e:
        print("*** WiFi ERROR: " + str(e))
        time.sleep(1)

def wlan_setup_sta():
    global wlan
    try:
        wlan = network.WLAN(network.STA_IF)
        wlan_mac = wlan.config('mac')
        print("MAC Address:", ubinascii.hexlify(wlan_mac, ':').decode())
        #print("RSSI:", wlan.status('rssi'))

        wlan.disconnect()
        wlan.active(False)
        wdt.feed()
        time.sleep(1)
        wlan.active(True)

        # Scanning for APs
        wlan_sec_map = {
                0: "OPEN",
                1: "WEP",
                2: "WPA-PSK",
                3: "WPA2-PSK",
                4: "WPA/WPA2-PSK"
            }
        print("Scanning for WiFi networks...")
        wdt.feed()
        wlans = wlan.scan()
        wdt.feed()
        for w in wlans:
            # (ssid, bssid, channel, RSSI, security, hidden)
            #print(w)
            security = w[4]
            if security in wlan_sec_map:
                sec_name = wlan_sec_map[security]
            else:
                sec_name = "%d" % security
            print("%-15s: ch=%-2d RSSI=%3d sec=%-13s hidden=%d" % (w[0].decode(), w[2], w[3], sec_name, w[5]))

        wlan.connect(config['ssid'], config['password'])

        max_wait = 10
        sys.stdout.write('\nWaiting for wifi connection')
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            max_wait -= 1
            sys.stdout.write('.')
            wdt.feed()
            time.sleep(1)
        print('')

        if wlan.status() != 3:
            raise RuntimeError('Network connection failed. Status=%d' % wlan.status())
        else:
            status = wlan.ifconfig()
            print('Connected: IP=%s' % status[0])
            if config['enable_oled']:
                oled.text(status[0], 0, 32)
                oled.show()

        for i in range(0, 3):
            led.on()
            time.sleep(.1)
            led.off()
            time.sleep(.1)
    except Exception as e:
        print("*** WiFi ERROR: " + str(e))
        time.sleep(1)

def wlan_setup():
    if not config['ap'] and len(config['ssid']) > 0 and len(config['password']) > 0:
        wlan_setup_sta()
    else:
        wlan_setup_ap()


wlan_setup()

# Create a stream poller
poller = select.poll()

s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
#s.setblocking(True)
addr = socket.getaddrinfo('0.0.0.0', 80)[0][-1]
s.bind(addr)
s.listen()
poller.register(s, select.POLLIN)
print('Http socket listening on port', addr[1])
http_clients = []

# Raw socket for relaying incoming serial data
raw_server = socket.socket()
raw_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
raw_server_addr = socket.getaddrinfo('0.0.0.0', 1234)[0][-1]
raw_server.bind(raw_server_addr)
raw_server.listen()
poller.register(raw_server, select.POLLIN)
print('Raw socket listening on port', raw_server_addr[1])
raw_clients = []

# Set up metric for energy
energy = Metric("p1_energy_kwhs", Metric.TYPE_COUNTER, ("type", "direction"))
energy.set_help("The accumulated meter value over all time")

# Set up metric for power
power = Metric("p1_power_watts", Metric.TYPE_GAUGE, ("type", "direction", "phase"))
power.set_help("Momentary power")

# Set up metric for voltage
voltage = Metric("p1_voltage_volts", Metric.TYPE_GAUGE, ("phase"))
voltage.set_help("Incoming voltage from grid")

# Set up metric for current
current = Metric("p1_current_amperes", Metric.TYPE_GAUGE, ("phase"))
current.set_help("Momentary current draw")

# Metric for applicaton uptime
uptime = Metric("p1_uptime_seconds", Metric.TYPE_COUNTER)
uptime.set_help("Uptime of the P1 exporter application")

temperature = Metric("p1_temperature_celcius", Metric.TYPE_GAUGE)
temperature.set_help("The temperature of the SOC")

# Map OBIS to related metric data
obis_map = {
    #"0-0:1.0.0": {
    #    "name": "Datum och tid"
    #    },
    "1-0:1.8.0": {
        "name": "Mätarställning Aktiv Energi Uttag.",
        "metric": energy,
        "labels": ("active", "consume")
        },
    "1-0:2.8.0": {
        "name": "Mätarställning Aktiv Energi Inmatning",
        "metric": energy,
        "labels": ("active", "produce")
        },
    "1-0:3.8.0": {
        "name": "Mätarställning Reaktiv Energi Uttag",
        "metric": energy,
        "labels": ("reactive", "consume")
        },
    "1-0:4.8.0": {
        "name": "Mätarställning Reaktiv Energi Inmatning",
        "metric": energy,
        "labels": ("reactive", "produce")
        },
    "1-0:1.7.0": {
        "name": "Aktiv Effekt Uttag",          # Momentan trefaseffekt
        "metric": power,
        "labels": ("active", "consume","all")
        },
    "1-0:2.7.0": {
        "name": "Aktiv Effekt Inmatning",      # Momentan trefaseffekt
        "metric": power,
        "labels": ("active", "produce","all")
        },
    "1-0:3.7.0": {
        "name": "Reaktiv Effekt Uttag",        # Momentan trefaseffekt
        "metric": power,
        "labels": ("reactive", "consume","all")
        },
    "1-0:4.7.0": {
        "name": "Reaktiv Effekt Inmatning",    # Momentan trefaseffekt
        "metric": power,
        "labels": ("reactive", "produce","all")
        },
    "1-0:21.7.0": {
        "name": "L1 Aktiv Effekt Uttag",       # Momentan effekt
        "metric": power,
        "labels": ("active", "consume", "L1")
        },
    "1-0:22.7.0": {
        "name": "L1 Aktiv Effekt Inmatning",   # Momentan effekt
        "metric": power,
        "labels": ("active", "produce", "L1")
        },
    "1-0:41.7.0": {
        "name": "L2 Aktiv Effekt Uttag",       # Momentan effekt
        "metric": power,
        "labels": ("active", "consume", "L2")
        },
    "1-0:42.7.0": {
        "name": "L2 Aktiv Effekt Inmatning",   # Momentan effekt
        "metric": power,
        "labels": ("active", "produce", "L2")
        },
    "1-0:61.7.0": {
        "name": "L3 Aktiv Effekt Uttag",       # Momentan effekt
        "metric": power,
        "labels": ("active", "consume", "L3")
        },
    "1-0:62.7.0": {
        "name": "L3 Aktiv Effekt Inmatning",   # Momentan effekt
        "metric": power,
        "labels": ("active", "produce", "L3")
        },
    "1-0:23.7.0": {
        "name": "L1 Reaktiv Effekt Uttag",     # Momentan effekt
        "metric": power,
        "labels": ("reactive", "consume", "L1")
        },
    "1-0:24.7.0": {
        "name": "L1 Reaktiv Effekt Inmatning", # Momentan effekt
        "metric": power,
        "labels": ("reactive", "produce", "L1")
        },
    "1-0:43.7.0": {
        "name": "L2 Reaktiv Effekt Uttag",     # Momentan effekt
        "metric": power,
        "labels": ("reactive", "consume", "L2")
        },
    "1-0:44.7.0": {
        "name": "L2 Reaktiv Effekt Inmatning", # Momentan effekt
        "metric": power,
        "labels": ("reactive", "produce", "L2")
        },
    "1-0:63.7.0": {
        "name": "L3 Reaktiv Effekt Uttag",     # Momentan effekt
        "metric": power,
        "labels": ("reactive", "consume", "L3")
        },
    "1-0:64.7.0": {
        "name": "L3 Reaktiv Effekt Inmatning", # Momentan effekt
        "metric": power,
        "labels": ("reactive", "produce", "L3")
        },
    "1-0:32.7.0": {
        "name": "L1 Fasspänning",              # Momentant RMS-värde
        "metric": voltage,
        "labels": ("L1")
        },
    "1-0:52.7.0": {
        "name": "L2 Fasspänning",              # Momentant RMS-värde
        "metric": voltage,
        "labels": ("L2")
        },
    "1-0:72.7.0": {
        "name": "L3 Fasspänning",              # Momentant RMS-värde
        "metric": voltage,
        "labels": ("L3")
        },
    "1-0:31.7.0": {
        "name": "L1 Fasström",                 # Momentant RMS-värde
        "metric": current,
        "labels": ("L1")
        },
    "1-0:51.7.0": {
        "name": "L2 Fasström",                 # Momentant RMS-värde
        "metric": current,
        "labels": ("L2")
        },
    "1-0:71.7.0": {
        "name": "L3 Fasström",                 # Momentant RMS-värde
        "metric": current,
        "labels": ("L3")
        }
    }

obis_display_order = [
    "1-0:1.8.0",
    "1-0:2.8.0",
    "1-0:3.8.0",
    "1-0:4.8.0",
    "1-0:1.7.0",
    "1-0:2.7.0",
    "1-0:3.7.0",
    "1-0:4.7.0",
    "1-0:21.7.0",
    "1-0:22.7.0",
    "1-0:41.7.0",
    "1-0:42.7.0",
    "1-0:61.7.0",
    "1-0:62.7.0",
    "1-0:23.7.0",
    "1-0:24.7.0",
    "1-0:43.7.0",
    "1-0:44.7.0",
    "1-0:63.7.0",
    "1-0:64.7.0",
    "1-0:32.7.0",
    "1-0:52.7.0",
    "1-0:72.7.0",
    "1-0:31.7.0",
    "1-0:51.7.0",
    "1-0:71.7.0"
    ]


def add_raw_client():
    try:
        cl, addr = raw_server.accept()
        cl.setblocking(True)
        print('### Raw client connected from', addr)
        poller.register(cl, select.POLLIN)
    except OSError as e:
        cl.close()
        return
    raw_clients.append(cl)


def remove_raw_client(cl):
    print("### Remove raw client")
    raw_clients.remove(cl)
    poller.unregister(cl)
    cl.close()
    

def add_http_client(cl):
    try:
        poller.register(cl, select.POLLIN)
    except OSError as e:
        cl.close()
        return
    http_clients.append(cl)
    print("### connected clients: %d" % len(http_clients))


def remove_http_client(cl):
    print("### Remove http client")
    http_clients.remove(cl)
    print("### connected clients: %d" % len(http_clients))
    poller.unregister(cl)
    cl.close()
    
def send_http_header(cl, code, headers=[]):
    code2str = {
        200: 'OK',
        303: 'See Other',
        404: 'NOT FOUND',
        }
    cl.write('HTTP/1.0 %d %s\r\n' % (code, code2str[code]))
    #headers.append('Connection: close')
    for header in headers:
        cl.write(header)
        cl.write('\r\n')
    cl.write('\r\n')
    
def send_html_header(cl, code, headers):
    send_http_header(cl, code, headers)
    cl.write('<html>\n')
    cl.write('<head><title>P1 Exporter</title><link rel="icon" type="image/x-icon" href="/favicon.ico"></head>\n')
    cl.write('<body>\n')

def send_html_trailer(cl):
    cl.write('</body></html>\r\n')
    cl.close()

def reply_with_error(cl, request, code):
    send_http_header(cl, code, ['Content-type: text/plain'])
    cl.write(request)
    cl.close()

def reply_with_index_page(cl):
    send_html_header(cl, 200, ['Content-type: text/html;charset=utf-8'])
    cl.write('<h1>P1 Exporter</h1>\n')
    
    cl.write('<a href="/metrics">Metrics</a>\n')
    cl.write('<p/>\n')
    
    cl.write('<a href="/config">Configuration</a>\n')
    cl.write('<p/>\n')
    
    cl.write('<table cellpadding="5">\n')
    cl.write('<tr><th>Beskrivning</th><th>Värde</th><th>Tidsstämpel</th></tr>\n')
    
    for obis in obis_display_order:
        obis_spec = obis_map[obis]
        value = '-'
        ts = '-'
        if "metric" in obis_spec:
            metric = obis_spec["metric"]
            value = metric.value(obis_spec["labels"])
            if value is None:
                value = '-'
            epoch_ms = metric.timestamp(obis_spec["labels"])
            if epoch_ms is not None:
                utc = time.gmtime(int(epoch_ms / 1000))
                ts = '%d-%02d-%02d %02d:%02d:%02dZ' % utc[0:6]
        cl.write('<tr><td>%s</td><td>%s</td><td>%s</td></tr>\n' % (obis_spec["name"], value, ts))
    cl.write('</table>\n')
    
    send_html_trailer(cl)

def reply_with_favicon(cl):
    print("### Send favicon")
    if 'favicon.ico' in uos.listdir('/'):
        send_http_header(cl, 200, ['Content-type: image/x-icon'])
        with open('/favicon.ico', 'rb') as f:
            cl.sendall(f.read())
    else:
        send_http_header(404)
    cl.close()
    print('### Done sending favicon')
    
def reply_with_config_page(cl):
    send_html_header(cl, 200, ['Content-type: text/html;charset=utf-8'])
    cl.write('<h1>P1 Exporter Configuration</h1>\n')
    cl.write('<form action="/save_config">\n')
    for input in CONFIG_VARS:
        if input['type'] == 'checkbox':
            cl.write('<input name="%s" value="" type="hidden"/>\n' % (input['name']))
            cl.write('<input id="%s" name="%s" type="checkbox" %s/>\n' % (input['name'], input['name'], 'checked' if config[input['name']] else ''))
            cl.write('<label for="%s">%s</label>\n' % (input['name'], input['text']))
        elif input['type'] == 'radio':
            for sel in input['selections']:
                cl.write('<input id="%s" name="%s" value="%s" type="radio" %s/>\n'
                         % (sel['id'], input['name'], sel['value'], 'checked' if sel['value'] == str(config[input['name']]) else ''))
                cl.write('<label for="%s">%s</label>\n' % (sel['id'], sel['text']))
        elif input['type'] == 'number':
            cl.write('<label for="%s">%s:</label>\n' % (input['name'], input['text']))
            cl.write('<input id="%s" name="%s" value="%s" type="number" min="%d" max="%d"/>\n'
                     % (input['name'], input['name'], config[input['name']], input['min'], input['max']))
        elif input['type'] in {'text', 'password'}:
            cl.write('<label for="%s">%s:</label>\n' % (input['name'], input['text']))
            cl.write('<input id="%s" name="%s" value="%s" type="%s"/>\n'
                     % (input['name'], input['name'], config[input['name']], input['type']))
        cl.write('<br/>')
    cl.write('<input type="reset" value="Reset"><input type="submit" value="Save">\n')
    cl.write('</form>\n')
    send_html_trailer(cl)

def unescape_form_value(val):
    unescaped = ''
    val = val.replace('+', ' ')
    begin = 0
    while True:
        pos = val.find('%', begin)
        if pos == -1:
            break
        unescaped += val[begin:pos] + chr(int(val[pos+1:pos+3], 16))
        begin = pos + 3
    unescaped += val[begin:]
    return unescaped
    
def reply_with_save_config(cl, request):
    req = request.decode()
    print(req)    
    send_http_header(cl, 303, ['Location: /', 'Retry-After: 20'])
    
    begin = req.find('?') + 1
    end = req.find(' ', begin)
    params_str = req[begin:end]
    begin = 0
    params = dict()
    while True:
        end = params_str.find('&', begin)
        if end == -1:
            param = params_str[begin:]
        else:
            param = params_str[begin:end]
        equals = param.find('=')
        pname = param[0:equals]
        pvalue = param[equals+1:]
        print(pname, pvalue)
        params[pname] = unescape_form_value(pvalue)
        if end == -1:
            break
        begin = end + 1
    
    for input in CONFIG_VARS:
        if input['name'] in params:
            config[input['name']] = type(input['default'])(params[input['name']])
    print(config)
    save_config()
    cl.close()
    reboot()

def send_openmetrics(cl):
    cl.write(uptime.headers())
    cl.write(uptime.value_rows())
    cl.write("\n")
    
    cl.write(temperature.headers())
    cl.write(temperature.value_rows())
    cl.write("\n")
    
    value_rows = energy.value_rows()
    if len(value_rows) > 0:
        cl.write(energy.headers())
        cl.write(value_rows)
        cl.write("\n")
    
    value_rows = power.value_rows()
    if len(value_rows) > 0:
        cl.write(power.headers())
        cl.write(value_rows)
        cl.write("\n")
    
    value_rows = voltage.value_rows()
    if len(value_rows) > 0:
        cl.write(voltage.headers())
        cl.write(value_rows)
        cl.write("\n")
    
    value_rows = current.value_rows()
    if len(value_rows) > 0:
        cl.write(current.headers())
        cl.write(value_rows)
        cl.write("\n")

def reply_with_openmetrics(cl, wait):
    send_http_header(cl, 200, ['Content-type: text/plain'])
    if wait:
        add_http_client(cl)
    else:
        send_openmetrics(cl)
        cl.close()

def process_http_request():
    try:
        cl, addr = s.accept()
        #cl.setblocking(True)
        cl.settimeout(2.5)
        print('### Http client connected from', addr)
        wdt.feed()
        request = cl.recv(1024)
        wdt.feed()
        print(request)
        if len(request) == 0:
            cl.close()
            return
    
        uptime.set_value(time.ticks_diff(time.ticks_ms(), starttime)/1000)
        
        reading = sensor_temp.read_u16() * conversion_factor 
        temp = 27 - (reading - 0.706)/0.001721
        print(temp)
        temperature.set_value(temp)
        
        if request.startswith('GET / '):
            reply_with_index_page(cl)
        elif request.startswith('GET /favicon.ico '):
            reply_with_favicon(cl)
        elif request.startswith('GET /config '):
            reply_with_config_page(cl)
        elif request.startswith('GET /save_config?'):
            reply_with_save_config(cl, request)
        elif request.startswith('GET /metrics '):
            reply_with_openmetrics(cl, False)
        elif request.startswith('GET /waitmetrics '):
            reply_with_openmetrics(cl, True)
        else:
            #print(request)
            reply_with_error(cl, request, 404)
    except OSError as e:
        print('OSError:', e)
        cl.close()
    print('### Http connection done')


# Enable pull-up on the UART rx pin
#Pin(config['uart_rx_gpio'], Pin.IN, Pin.PULL_UP)

# Set up the UART for receiving P1 data
uart1 = UART(
    config['uart_no'],
    baudrate=config['uart_baudrate'],
    bits=config['uart_bits'],
    parity=None,
    stop=1,
    tx=Pin(config['uart_tx_gpio']),
    rx=Pin(config['uart_rx_gpio']),
    rxbuf=1024,
    invert=UART.INV_RX)
#uart1.write('\nhello\n')
poller.register(uart1, select.POLLIN)

values = dict()

def oled_print_obis(obis, decimals, with_unit, x, y):
    global values
    if obis in values:
        val = values[obis]
        txt = ("%." + str(decimals) + "f") % float(val["value"])
        if with_unit:
            txt += val["unit"]
    else:
        txt = "N/A"
    oled.text(txt, x, y)


def oled_print_three_phase(measurement_code, decimals, row):
    obis = "1-0:%02d.7.0" % (measurement_code)
    oled_print_obis(obis, decimals, False, 0, row)
    obis = "1-0:%02d.7.0" % (measurement_code + 20)
    oled_print_obis(obis, decimals, False, 38, row)
    obis = "1-0:%02d.7.0" % (measurement_code + 40)
    oled_print_obis(obis, decimals, False, 76, row)
    oled.text("%s" % (values[obis]["unit"]), 112, row)
    

def decode_p1_msg(msg):
    global values
    
    #print(msg.decode())
    line_re = re.compile("[\r\n]")
    flag_re = re.compile("^(...)(.)(.*)$")
    ts_re = re.compile(r"^(\d\d\d\d)(\d\d)(\d\d)(\d\d)(\d\d)(\d\d).$")

    lines = line_re.split(msg.decode())
    match = flag_re.match(lines[0])
    if not match:
        return
    
    led.on()
    
    manufacturer = match.group(1)
    speed = match.group(2)
    meter_id = match.group(3)
    print("manufacturer=", manufacturer)
    print("speed=", speed)
    print("id=", meter_id)
    
    timestamp = None
    for line in lines[1:]:
        #print(line)
        match = re.match("^([^(]+)\(([^*]+)(\*(.*))?\)$", line)
        if match:
            obis = match.group(1)
            value = match.group(2)
            unit = match.group(4)
            if unit is None:
                unit = ''
                
            if obis == "0-0:1.0.0":
                match = ts_re.match("20" + value)
                if match:
                    the_time = tuple(int(el) for el in match.groups())
                    timestamp = 1000 * (time.mktime(the_time + (0, 0)) - config['tz_offset'])
                    print(timestamp / 1000)
                    continue

            obis_spec = None
            if obis in obis_map:
                obis_spec = obis_map[obis]
                name = obis_spec['name']
            else:
                name = obis
            print(name + ': ' + value + unit)
            values[obis] = {
                "value": value,
                "unit": unit
                }
            if obis_spec is not None and "metric" in obis_spec:
                metric = obis_spec["metric"]
                labels = obis_spec["labels"]
                #print(labels)
                metric.set_value(value, labels, timestamp)

    if config['enable_oled']:
        # Clear screen
        oled.fill(0)
        
        # Datum och tid
        row = 0
        row_inc = 8
        
        oled.text(manufacturer + meter_id, 0, row)
        row += row_inc
        
        obis = "0-0:1.0.0"
        if obis in values:
            val = values[obis]
            oled.text("%s" % (val["value"]), 0, row)
        else:
            oled.text("N/A", 0, row)
        row += row_inc
        
        # Mätarställning Aktiv/Reaktiv Energi Uttag
        oled_print_obis("1-0:1.8.0", 0, True, 0, row)
        row += row_inc
        oled_print_obis("1-0:3.8.0", 0, True, 0, row)
        row += row_inc
        
        # Aktiv/Reaktiv Effekt Uttag, momentan trefaseffekt
        oled_print_obis("1-0:1.7.0", 1, True, 0, row)
        oled_print_obis("1-0:3.7.0", 1, True, 64, row)
        row += row_inc

        # Aktiv Effekt Uttag (L1, L2, L3)
        oled_print_three_phase(21, 1, row)
        row += row_inc
        
        # Fasström (L1, L2, L3)
        oled_print_three_phase(31, 1, row)
        row += row_inc

        # Fasspänning (L1, L2, L3)
        oled_print_three_phase(32, 0, row)
        row += 12
        
        oled.show()

    for cl in http_clients[:]:
        try:
            send_openmetrics(cl)
        except OSError as e:
            print(e)
        remove_http_client(cl)

    led.off()

msg = None
def uart_rx():
    global msg
    data = uart1.read()
    print("### data=", data)
    #uart1.write(data)

    for cl in raw_clients[:]:
        try:
            cl.write(data)
        except OSError as e:
            remove_raw_client(cl)

    while data is not None and len(data) > 0:
        if msg is None:
            pos = data.find(b'/')
            if pos > -1:
                data = data[pos+1:]
                msg = b''
            else:
                data = ''
        if msg is not None:
            pos = data.find(b'!')
            if pos > -1:
                msg += data[0:pos]
                #crc = data[pos+1:pos+5]
                #print(msg.decode() + '\nCRC=' + crc.decode())
                decode_p1_msg(msg)
                msg = None
                data = data[pos+1:]
            else:
                msg += data
                data = ''
                

while True:
        events = poller.poll(1000)
        wdt.feed()
        if wlan.status() != 3:
            wlan_setup()
        for desc, event in events:
            if desc == raw_server and event == select.POLLIN:
                add_raw_client()
            for cl in raw_clients[:]:
                if desc == cl and event == select.POLLIN:
                    data = cl.read(1)
                    print("### Raw read: len=%d" % len(data))
                    if len(data) == 0:
                        remove_raw_client(cl)
            for cl in http_clients[:]:
                if desc == cl and event == select.POLLIN:
                    data = cl.read(1)
                    print("### Http read: len=%d" % len(data))
                    if len(data) == 0:
                        remove_http_client(cl)
            if desc == s and event == select.POLLIN:
                process_http_request()
            if desc == uart1 and event == select.POLLIN:
                uart_rx()

