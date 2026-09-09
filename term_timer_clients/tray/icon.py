"""The cube drawn small enough to live in a bar."""
from functools import lru_cache

# One pixel of the icon, as the pixmap carries it: red, green, blue and
# how much of it there is at all.
Pixel = tuple[int, int, int, int]

# One face of the drawn cube, as a corner and the two sides leaving it.
Rhombus = tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]

# The sizes the icon is handed over in, and **the size a bar asks for
# has to be among them**: a shell takes the smallest pixmap at least as
# big as the box it draws in and scales it down, so a panel 16 pixels
# tall handed a 22 draws a cube through a resampling that softens every
# diagonal it is made of - and a soft cube in a bar reads as a small
# one. So the two sizes a panel is ever built at are drawn, and each
# again at twice itself for the scaled display that asks for it.
ICON_SIZES = (16, 22, 32, 44)

# How much of the icon the cube itself takes. What is left is the room
# the outline needs to be seen at all, and nothing more: the room
# between two icons is put there by the bar, and a share kept here on
# top of it is an icon that reads as smaller than its neighbours for no
# reason anybody can see.
CUBE_SHARE = 0.48

# Half the width of the hexagon, against half its height. **Every ratio
# tiles it** - the three rhombi are read off the same six points, and
# stretching them sideways is one affine transform of the whole cube -
# so what this number picks is the corner the cube is seen from, and
# nothing else: `sqrt(3) / 2` is the isometric one, the three faces of
# equal area, and it draws a hexagon taller than it is wide. **The box
# an icon is drawn in is square**, and it is scaled to that box whole,
# so an isometric cube spends its width on nothing: the same cube one
# corner higher fills the box in both directions and is a quarter
# bigger for it, which is the whole of what a bar shows of it.
FLAT_SHARE = 1.0

# How thick the outline around the cube is, against the size of the
# icon. **The outline is what makes the icon readable on both bars**: a
# GNOME bar is dark and a light theme is not, and a cube drawn on its
# colors alone disappears into one of the two. A dark rim under light
# faces is seen against either. Thick enough to still be a pixel of
# its own at the smallest size drawn: a rim thinning away with the icon
# is a rim the bar it was drawn for no longer has.
OUTLINE_SHARE = 0.07

# How many samples a pixel is drawn from, on each axis. An icon this
# small is all diagonals, and a diagonal drawn without them is the
# staircase an icon is recognised by rather than the cube.
SAMPLES = 3

# What is under the cube, and what is around it. Nothing is drawn on
# the ground of the bar, which belongs to a theme this client knows
# nothing about.
NOTHING: Pixel = (0, 0, 0, 0)

OUTLINE: Pixel = (26, 26, 26, 200)

# The three faces of a cube that is there, in the order they are drawn:
# the one on top, the one on the left, the one on the right. They are
# the colors of a cube rather than of a palette - white, blue and red
# is what a cube looks like to anybody who has held one - and the top
# is the lightest of the three, which is what makes the three read as
# one solid rather than as three lozenges.
# **The faces carry the icon on a dark bar and the rim carries it on a
# light one**, and that is why they are as light as they are: a rim of
# graphite is worth nothing against a panel of graphite, so what is
# left to be seen there is the color itself, and a blue and a red taken
# from a sticker are two thirds of a cube gone dim. Lifted until each
# of them stands against a dark panel on its own - and the top face
# stays the lightest of the three, which is what makes the three read
# as one solid rather than as three lozenges.
LIVE_FACES: tuple[Pixel, Pixel, Pixel] = (
    (245, 245, 245, 255),
    (62, 139, 255, 255),
    (255, 92, 78, 255),
)

# The very same cube with the color taken out of it, and **not** a
# fainter one: an icon dimmed by its alpha reads as a bar that is busy,
# where a cube gone grey reads as a cube that is not there. The three
# greys keep the three faces apart, so the shape stays a cube and only
# the cube stays away.
DORMANT_FACES: tuple[Pixel, Pixel, Pixel] = (
    (208, 208, 208, 255),
    (124, 124, 124, 255),
    (162, 162, 162, 255),
)


def faces(radius: float) -> tuple[Rhombus, Rhombus, Rhombus]:
    """
    Describe the three faces of a cube seen by its corner.

    The six points of the hexagon and the center it is drawn around are
    all it takes: every face is the corner it starts from and the two
    sides leaving it, and the three of them tile the hexagon exactly.

    Args:
        radius: Half the height of the cube, in pixels.

    Returns:
        The top, left and right faces, in the order they are read.

    """
    flat = radius * FLAT_SHARE
    half = radius / 2

    return (
        ((-flat, -half), (flat, -half), (flat, half)),
        ((-flat, -half), (0.0, radius), (flat, half)),
        ((flat, -half), (0.0, radius), (-flat, half)),
    )


def within(point: tuple[float, float], face: Rhombus) -> bool:
    """
    Tell whether a point falls on one face of the cube.

    Args:
        point: Where the sample is taken, from the center of the icon.
        face: The face, as a corner and the two sides leaving it.

    Returns:
        True when the point lies on that face.

    """
    (origin_x, origin_y), (first_x, first_y), (second_x, second_y) = face

    span = first_x * second_y - first_y * second_x
    if not span:
        return False

    x = point[0] - origin_x
    y = point[1] - origin_y

    along = (x * second_y - y * second_x) / span
    across = (first_x * y - first_y * x) / span

    return 0.0 <= along <= 1.0 and 0.0 <= across <= 1.0


def shade(point: tuple[float, float], radius: float, palette: tuple[
        Pixel, Pixel, Pixel,
]) -> Pixel:
    """
    Tell what color the cube wears where a sample was taken.

    The outline is the very same cube drawn wider: the three faces tile
    the hexagon exactly, so what is left between the two is a rim of
    one thickness all around, and no edge has to be drawn as a line.

    Args:
        point: Where the sample is taken, from the center of the icon.
        radius: Half the height of the cube, in pixels.
        palette: The colors of the three faces.

    Returns:
        The color at that point, transparent where the cube is not.

    """
    inner = radius * (1.0 - OUTLINE_SHARE * 2)

    for color, face in zip(palette, faces(inner), strict=True):
        if within(point, face):
            return color

    for face in faces(radius):
        if within(point, face):
            return OUTLINE

    return NOTHING


def average(samples: list[Pixel]) -> Pixel:
    """
    Blend what was found under one pixel into the pixel itself.

    The color is weighed by how much of it there is: averaging the
    channels flat would let the black of the outline bleed into what is
    merely transparent next to it, and edge every face with a grey halo.

    Args:
        samples: The colors found under the pixel.

    Returns:
        The color of the pixel.

    """
    weight = sum(sample[3] for sample in samples)

    if not weight:
        return NOTHING

    return (
        round(sum(sample[0] * sample[3] for sample in samples) / weight),
        round(sum(sample[1] * sample[3] for sample in samples) / weight),
        round(sum(sample[2] * sample[3] for sample in samples) / weight),
        round(weight / len(samples)),
    )


def pixmap(size: int, *, connected: bool) -> tuple[int, int, bytes]:
    """
    Draw the icon a bar shows, at the size it asks for.

    Args:
        size: Width and height of the icon, in pixels.
        connected: Whether there is a cube behind the stream.

    Returns:
        The width, the height and the pixels, as ARGB32 in the network
        byte order the tray protocol reads them in.

    """
    palette = LIVE_FACES if connected else DORMANT_FACES
    radius = size * CUBE_SHARE
    center = size / 2
    step = 1 / (SAMPLES + 1)

    pixels = bytearray()

    for row in range(size):
        for column in range(size):
            samples = [
                shade(
                    (
                        column + (across + 1) * step - center,
                        row + (down + 1) * step - center,
                    ),
                    radius,
                    palette,
                )
                for down in range(SAMPLES)
                for across in range(SAMPLES)
            ]

            red, green, blue, alpha = average(samples)
            pixels += bytes((alpha, red, green, blue))

    return size, size, bytes(pixels)


@lru_cache(maxsize=2)
def pixmaps(*, connected: bool) -> tuple[tuple[int, int, bytes], ...]:
    """
    Draw the icon at every size a bar may ask for.

    Kept once drawn, and there are only ever two of them: the bar reads
    the icon back whenever it feels like it - a menu opening, a screen
    changing - and a cube sampled pixel by pixel is tens of
    milliseconds. Handed back as a tuple for that reason: what is
    shared by every reader is what none of them may write in.

    Args:
        connected: Whether there is a cube behind the stream.

    Returns:
        The icons, smallest first.

    """
    return tuple(pixmap(size, connected=connected) for size in ICON_SIZES)
