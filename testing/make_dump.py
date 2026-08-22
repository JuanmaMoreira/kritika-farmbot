import uiautomator2 as u2

d = u2.connect("GIGET4NNZ9CIOJKN")

input("Abrí la ad y presioná ENTER cuando veas el botón...")

nodes = d.xpath('//*[@content-desc="Close"]')

for node in nodes.all():
    bounds = node.attrib.get("bounds")
    print("Bounds:", bounds)

    # parsear bounds
    import re
    nums = list(map(int, re.findall(r'\d+', bounds)))
    x1, y1, x2, y2 = nums

    cx = (x1 + x2) // 2
    cy = (y1 + y2) // 2

    print(f"Click en ({cx}, {cy})")
    d.click(cx, cy)