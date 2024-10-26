import colorsys


def cie_xy_to_rgb(x, y, brightness=1.0):
    """
    Convert CIE 1931 xy chromaticity coordinates to RGB.

    Args:
        x (float): x chromaticity coordinate (0.0 to 1.0)
        y (float): y chromaticity coordinate (0.0 to 1.0)
        brightness (float): Brightness level (0.0 to 1.0)

    Returns:
        tuple: (r, g, b) values normalized to 0-1
    """
    # Calculate z from x and y
    z = 1.0 - x - y

    # Calculate XYZ values
    Y = brightness
    X = (Y / y) * x
    Z = (Y / y) * z

    # XYZ to RGB conversion matrix (sRGB D65)
    r = X * 3.2404542 + Y * -1.5371385 + Z * -0.4985314
    g = X * -0.9692660 + Y * 1.8760108 + Z * 0.0415560
    b = X * 0.0556434 + Y * -0.2040259 + Z * 1.0572252

    # Clip values to 0-1 range
    r = max(0.0, min(1.0, r))
    g = max(0.0, min(1.0, g))
    b = max(0.0, min(1.0, b))

    # Gamma correction
    if r <= 0.0031308:
        r = 12.92 * r
    else:
        r = 1.055 * (r ** (1.0 / 2.4)) - 0.055

    if g <= 0.0031308:
        g = 12.92 * g
    else:
        g = 1.055 * (g ** (1.0 / 2.4)) - 0.055

    if b <= 0.0031308:
        b = 12.92 * b
    else:
        b = 1.055 * (b ** (1.0 / 2.4)) - 0.055

    return (r, g, b)


def cie_xy_to_hsv(x, y, brightness=1.0):
    """
    Convert CIE 1931 xy chromaticity coordinates to HSV.

    Args:
        x (float): x chromaticity coordinate (0.0 to 1.0)
        y (float): y chromaticity coordinate (0.0 to 1.0)
        brightness (float): Brightness level (0.0 to 1.0)

    Returns:
        tuple: (hue, saturation, value) all in range 0-1
    """
    # First convert to RGB
    rgb = cie_xy_to_rgb(x, y, brightness)

    # Then convert RGB to HSV using colorsys
    hsv = colorsys.rgb_to_hsv(*rgb)

    return hsv


# Example usage:
if __name__ == "__main__":
    # x, y = 0.6400, 0.3300  # Red
    x, y = 0.3000, 0.6000  # Green
    # x, y = 0.1500, 0.0600  # Blue
    # x, y = 0.3127, 0.3291  # White
    brightness = 1.0

    # x, y, brightness = 0.55, 0.3, 200 / 254

    print(f"CIE xy ({x}, {y}) with brightness {brightness}")
    r, g, b = cie_xy_to_rgb(x, y, brightness)
    print(f"-> RGB: R={r*255:.3f}, G={g*255:.3f}, B={b*255:.3f}")

    hsv = cie_xy_to_hsv(x, y, brightness)
    print(f"-> HSV: H={hsv[0]*360:.1f}°, S={hsv[1]*100:.1f}%, V={hsv[2]*100:.1f}%")
