ipAddress = '172.16.0.21'
light_keys = ['label','wavelength', 'color', 'triggerLine','simtheta','port','device']
WAVELENGTH_TO_COLOR = {
    405: (180, 30, 230),
    488: (40, 130, 180),
    532: (80, 255, 0),
    561: (176, 255, 0),
    593: (255,200,0),
    640: (255, 40, 40),
    'white': (255, 255, 255)
}
lights = [
    ('ambient', 'Ambient', WAVELENGTH_TO_COLOR['white'], 0),
    ('405nm', 405, WAVELENGTH_TO_COLOR[405], 1<<13,),
    ('488nm', 488, WAVELENGTH_TO_COLOR[488], 1<<9,),
    ('532nm', 532, WAVELENGTH_TO_COLOR[532], 1<<14,),
    ('593nm', 593, WAVELENGTH_TO_COLOR[593], 1<<12,),
    ('DIC', 'DIC', WAVELENGTH_TO_COLOR['white'], 1<<15,),]
