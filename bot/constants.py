# bot/constants.py

import os
from dotenv import load_dotenv

# Carga las variables del archivo .env
load_dotenv()

# Si no encuentra la variable en el .env, usa el valor por defecto
DISPOSITIVO_ADB = os.getenv("DISPOSITIVO_ADB", "SERIAL_POR_DEFECTO") # serial USB, no IP
SCRCPY_SERVER_PATH = os.getenv("SCRCPY_SERVER_PATH", r"ruta\generica\scrcpy-server")
ADB_PATH = "adb"                  # o ruta completa si no está en PATH

# ====================
# Configuración global
# ====================

RESOLUCION_BASE = (1224, 2712)

# Tiempo de espera por defecto entre acciones (en segundos)
DEFAULT_DELAY = 0.3

# Modo debug: muestra imágenes de matching y prints de confianza.
# Poner en False para producción.
DEBUG = False

# ====================
# Contextos
# ====================

# Datos de detección de cada contexto reconocible del juego.
# Formato de region: (x1, y1, x2, y2) — coordenadas absolutas basadas en RESOLUCION.
#
# Campos obligatorios:
#   imagen                  ruta al template usado para detectarlo
#   region                  zona de la pantalla donde buscar el template
#   threshold               confianza mínima para considerar el contexto detectado (0.0 - 1.0)
#   menu_rapido_disponible  si el menú rápido está activo en este contexto
#   menu_rapido_tipo        clave en MENU_RAPIDO_OFFSET que aplica a este contexto
#   botones                 coordenadas (x, y) de botones siempre disponibles en este contexto
#
# Campos opcionales:
#   menus        menús desplegables transitorios (se cierran al hacer click fuera).
#                Cada menú tiene imagen+region para detectar si está abierto, y sus propios botones.
#   subcontexto  variantes persistentes y mutuamente excluyentes del mismo contexto
#                (ej: en qué episodio estás dentro de stage_normal).
#                Tiene "tipo" (nombre descriptivo) y "valores", donde cada valor tiene
#                imagen+region para detectarlo, y opcionalmente botones propios.

CONTEXTOS_DEFINIDOS = {
    "lobby": {
        "imagen": "assets/ui/lobby-id.png",
        "region": (0.2039, 0.0302, 0.2434, 0.0899),
        "threshold":              0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "lobby",
        "botones": {
            "season-pass": {"coords": (0.0678, 0.2018), "outcomes": {}, "timeout": 5},
            "time-rewards": {"coords": (0.0619, 0.3162), "outcomes": {}, "timeout": 5},
            "menu-rapido": {"coords": (0.0789, 0.0654), "outcomes": {}, "timeout": 5},
            "shop": {"coords": (0.0793, 0.8815), "outcomes": {}, "timeout": 5},
            "black-market": {"coords": (0.1667, 0.893), "outcomes": {}, "timeout": 5},
            "trading-center": {"coords": (0.2441, 0.893), "outcomes": {}, "timeout": 5},
            "buffs": {"coords": (0.5852, 0.9101), "outcomes": {}, "timeout": 5},
            "quests": {"coords": (0.653, 0.9126), "outcomes": {}, "timeout": 5},
            "treasure": {"coords": (0.722, 0.9167), "outcomes": {}, "timeout": 5},
            "enhance": {"coords": (0.795, 0.9297), "outcomes": {}, "timeout": 5},
            "craft": {"coords": (0.8536, 0.9093), "outcomes": {}, "timeout": 5},
            "combine": {"coords": (0.9237, 0.9191), "outcomes": {}, "timeout": 5},
            "meteorites": {"coords": (0.9296, 0.7753), "outcomes": {}, "timeout": 5},
            "pets": {"coords": (0.8599, 0.7745), "outcomes": {}, "timeout": 5},
            "socket": {"coords": (0.795, 0.777), "outcomes": {}, "timeout": 5},
            "skills": {"coords": (0.7209, 0.7704), "outcomes": {}, "timeout": 5},
            "inventory": {"coords": (0.6479, 0.7884), "outcomes": {}, "timeout": 5},
            "awakening": {"coords": (0.58, 0.7884), "outcomes": {}, "timeout": 5},
            "battle": {"coords": (0.8529, 0.598), "outcomes": {}, "timeout": 5},
            "survival": {"coords": (0.8097, 0.4297), "outcomes": {}, "timeout": 5},
            "stage": {"coords": (0.8138, 0.2876), "outcomes": {}, "timeout": 5},
            "companion": {"coords": (0.6504, 0.6095), "outcomes": {}, "timeout": 5},
            "guild": {"coords": (0.7891, 0.0858), "outcomes": {}, "timeout": 5},
            "friends": {"coords": (0.8374, 0.0784), "outcomes": {}, "timeout": 5},
            "mailbox": {"coords": (0.8886, 0.0694), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None,
    },
    "select-character": {
        "imagen": "assets/ui/select-character-id.png",
        "region": (0.3971, 0.0417, 0.6036, 0.134),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "select": {"coords": (0.6855, 0.9101), "outcomes": {}, "timeout": 5},
            "last-character-after-scroll": {"coords": (0.7754, 0.5964), "outcomes": {}, "timeout": 5}
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage_normal": {
        "imagen": "assets/ui/stage-normal-id.png",
        "region": (0.3411, 0.8358, 0.4082, 0.884),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.198, 0.0694), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8009, 0.067), "outcomes": {}, "timeout": 5},
            "elite": {"coords": (0.8035, 0.1789), "outcomes": {}, "timeout": 5},
            "menu-world-map": {"coords": (0.7305, 0.1895), "outcomes": {}, "timeout": 5},
            "dispatch": {"coords": (0.6726, 0.1928), "outcomes": {}, "timeout": 5},
            "x4-stamina": {"coords": (0.8105, 0.9216), "outcomes": {}, "timeout": 5},
            "x3-stamina": {"coords": (0.7629, 0.9142), "outcomes": {}, "timeout": 5},
            "x2-stamina": {"coords": (0.7176, 0.9126), "outcomes": {}, "timeout": 5},
            "x1-stamina": {"coords": (0.6718, 0.9118), "outcomes": {}, "timeout": 5},
            "daily-dungeon": {"coords": (0.5697, 0.9003), "outcomes": {}, "timeout": 5},
            "claim": {"coords": (0.427, 0.933), "outcomes": {}, "timeout": 5},
            "prev-ep": {"coords": (0.0409, 0.54), "outcomes": {}, "timeout": 5},
            "next-ep": {"coords": (0.9838, 0.54), "outcomes": {}, "timeout": 5}
        },
        "menus": {
            "world-map": {
                "imagen": "assets/ui/world-map-menu-id.png",
                "region": (0.1777, 0.2672, 0.2201, 0.2925),
                "botones": {
                    "ep-01": {"coords": (0.2024, 0.1544), "outcomes": {}, "timeout": 5},
                    "ep-02": {"coords": (0.2526, 0.1569), "outcomes": {}, "timeout": 5},
                    "ep-03": {"coords": (0.3119, 0.1609), "outcomes": {}, "timeout": 5},
                    "ep-04": {"coords": (0.3654, 0.1536), "outcomes": {}, "timeout": 5},
                    "ep-05": {"coords": (0.4174, 0.1503), "outcomes": {}, "timeout": 5},
                    "ep-06": {"coords": (0.476, 0.1503), "outcomes": {}, "timeout": 5},
                    "ep-07": {"coords": (0.5262, 0.152), "outcomes": {}, "timeout": 5},
                    "ep-08": {"coords": (0.5852, 0.1528), "outcomes": {}, "timeout": 5},
                    "ep-09": {"coords": (0.6375, 0.1544), "outcomes": {}, "timeout": 5},
                    "ep-10": {"coords": (0.6932, 0.1528), "outcomes": {}, "timeout": 5},
                    "ep-11": {"coords": (0.198, 0.2541), "outcomes": {}, "timeout": 5},
                    "ep-12": {"coords": (0.2577, 0.2598), "outcomes": {}, "timeout": 5},
                    "ep-13": {"coords": (0.3105, 0.2565), "outcomes": {}, "timeout": 5},
                    "ep-14": {"coords": (0.3599, 0.2549), "outcomes": {}, "timeout": 5},
                    "close": {"coords": (0.7382, 0.2132), "outcomes": {}, "timeout": 5},
                },
            }
        },
        "subcontexto": {
            "tipo": "episodio",
            "valores": {
                "ep-14": {
                    "imagen":  "assets/ui/ep-14-id.png",
                    "region": (0.3009, 0.5335, 0.4152, 0.598),
                    "botones": {
                        "stage-01": {"coords": (0.2294, 0.3668), "outcomes": {}, "timeout": 5},
                        "stage-02": {"coords": (0.3411, 0.4346), "outcomes": {}, "timeout": 5},
                        "stage-03": {"coords": (0.444, 0.3685), "outcomes": {}, "timeout": 5},
                        "stage-04": {"coords": (0.5542, 0.4404), "outcomes": {}, "timeout": 5},
                        "stage-05": {"coords": (0.6541, 0.3709), "outcomes": {}, "timeout": 5},
                        "stage-06": {"coords": (0.7625, 0.4632), "outcomes": {}, "timeout": 5},
                        "stage-07": {"coords": (0.7592, 0.7386), "outcomes": {}, "timeout": 5},
                        "stage-08": {"coords": (0.6622, 0.6528), "outcomes": {}, "timeout": 5},
                        "stage-09": {"coords": (0.556, 0.75), "outcomes": {}, "timeout": 5}
                    }
                }
            }
        },
    },
    "stage-normal-selected": {
        "imagen": "assets/ui/stage-normal-selected-id.png",
        "region": (0.1792, 0.1422, 0.2349, 0.2623),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "x1": {"coords": (0.4369, 0.1062), "outcomes": {}, "timeout": 5},
            "x2": {"coords": (0.4882, 0.1087), "outcomes": {}, "timeout": 5},
            "x3": {"coords": (0.5365, 0.1062), "outcomes": {}, "timeout": 5},
            "x4": {"coords": (0.5878, 0.1111), "outcomes": {}, "timeout": 5},
            "buff-1": {"coords": (0.5391, 0.5384), "outcomes": {}, "timeout": 5},
            "buff-2": {"coords": (0.6125, 0.5343), "outcomes": {}, "timeout": 5},
            "buff-3": {"coords": (0.6869, 0.5221), "outcomes": {}, "timeout": 5},
            "buff-4": {"coords": (0.7585, 0.5261), "outcomes": {}, "timeout": 5},
            "difficulty-1": {"coords": (0.2345, 0.9126), "outcomes": {}, "timeout": 5},
            "difficulty-2": {"coords": (0.3079, 0.9093), "outcomes": {}, "timeout": 5},
            "difficulty-3": {"coords": (0.3827, 0.8995), "outcomes": {}, "timeout": 5},
            "difficulty-4": {"coords": (0.4513, 0.8938), "outcomes": {}, "timeout": 5},
            "get-support": {"coords": (0.7459, 0.7917), "outcomes": {}, "timeout": 5},
            "start": {"coords": (0.7364, 0.9118), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.8042, 0.174), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "mao-support",
            "valores": {
                "purchased": {
                    "imagen": "assets/ui/mao-purchased-id.png",
                    "region": (0.6497, 0.7402, 0.7017, 0.7908)
                },
                "not-purchased": {
                    "imagen": "assets/ui/mao-not-purchased-id.png",
                    "region": (0.6556, 0.741, 0.6999, 0.7925),
                },
                "activated": {
                    "imagen": "assets/ui/mao-activated.png",
                    "region": (0.5398, 0.7459, 0.6386, 0.7908),
                }
            }
        },
    },
    "stage-normal-selected-start": {
        "imagen": "assets/ui/stage-normal-selected-start-id.png",
        "region": (0.3348, 0.1119, 0.455, 0.1732),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "start": {"coords": (0.5737, 0.8913), "outcomes": {}, "timeout": 5},
            "auto": {"coords": (0.4192, 0.8905), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.6622, 0.098), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-normal-selected-start-auto": {
        "imagen": "assets/ui/stage-normal-selected-start-auto-id.png",
        "region": (0.4628, 0.1977, 0.5985, 0.2402),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "max": {"coords": (0.3348, 0.7982), "outcomes": {}, "timeout": 5},
            "video": {"coords": (0.3569, 0.8971), "outcomes": {}, "timeout": 5},
            "auro-repeat": {"coords": (0.5527, 0.9052), "outcomes": {}, "timeout": 5},
            "auto-continue": {"coords": (0.7279, 0.902), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.8326, 0.0474), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "config",
            "valores": {
                "max": {
                    "imagen": "assets/ui/checkbox-marked.png",
                    "region": (0.319, 0.7484, 0.3588, 0.8227),
                },
            },
        },
    },
    "stage-normal-selected-mao-support": {
        "imagen": "assets/ui/stage-normal-selected-mao-support-id.png",
        "region": (0.4056, 0.0899, 0.6165, 0.1577),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "fill-all": {"coords": (0.5988, 0.8472), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.7397, 0.0842), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "estado",
            "valores": {
                "purchased": {
                    "imagen": "assets/ui/mao-purchased-button-id.png",
                    "region": (0.517, 0.8145, 0.6342, 0.8766)
                }
            }
        },
    },
    "stage-normal-skip-completed": {
        "imagen": "assets/ui/stage-normal-skip-completed-id.png",
        "region": (0.3437, 0.1953, 0.6541, 0.2516),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4974, 0.8611), "outcomes": {}, "timeout": 5}
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-normal-daily-dungeon": {
        "imagen": "assets/ui/stage-normal-daily-dungeon-id.png",
        "region": (0.4322, 0.0752, 0.5612, 0.1275),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "buff-1": (0.5221, 0.5547),
            "buff-2": (0.618, 0.5588),
            "buff-3": (0.677, 0.5474),
            "buff-4": (0.7577, 0.5547),
            "close": (0.8097, 0.1021),
            "penance": (0.4296, 0.8791),
            "start": (0.7227, 0.8366),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "selected",
            "valores": {
                "penance": {
                    "imagen": "assets/ui/daily-dungeon-penance-selected.png",
                    "region": (0.3827, 0.8121, 0.4764, 0.8701),
                },
                # se puede ampliar confirmacion de buffs seleccionados
            }
        },
    },
    "stage-elite-chaos": {
        "imagen": "assets/ui/stage-elite-chaos-id.png",
        "region": (0.3514, 0.8358, 0.3901, 0.8799),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": {"coords": (0.1921, 0.0613), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.806, 0.0588), "outcomes": {}, "timeout": 5},
            "elite-chest1": {"coords": (0.5236, 0.8775), "outcomes": {}, "timeout": 5},
            "elite-chest2": {"coords": (0.6154, 0.8799), "outcomes": {}, "timeout": 5},
            "elite-chest3": {"coords": (0.705, 0.8709), "outcomes": {}, "timeout": 5},
            "elite-chest4": {"coords": (0.7924, 0.8775), "outcomes": {}, "timeout": 5},
            "claim": {"coords": (0.4207, 0.9322), "outcomes": {}, "timeout": 5},
            "stage-normal": {"coords": (0.8053, 0.1822), "outcomes": {}, "timeout": 5},
            "elite-chaos": {"coords": (0.7364, 0.1822), "outcomes": {}, "timeout": 5}, # switchs between elite and chaos
        },
        "menus":       {},
        "subcontexto": { # falta tomar el subcontexto de los cofres
            "tipo": "episodio",
            "valores": {
                "elite": {
                    "imagen": "assets/ui/stage-elite-ep-id.png",
                    "region": (0.7176, 0.2075, 0.7655, 0.2484),
                    "botones": {
                        "01": {"coords": (0.2117, 0.4158), "outcomes": {}, "timeout": 5},
                        "02": {"coords": (0.3112, 0.4183), "outcomes": {}, "timeout": 5},
                        "03": {"coords": (0.4063, 0.4134), "outcomes": {}, "timeout": 5},
                        "04": {"coords": (0.5018, 0.4232), "outcomes": {}, "timeout": 5},
                        "05": {"coords": (0.5959, 0.4248), "outcomes": {}, "timeout": 5},
                        "06": {"coords": (0.6965, 0.4208), "outcomes": {}, "timeout": 5},
                        "07": {"coords": (0.7858, 0.4118), "outcomes": {}, "timeout": 5},
                        "08": {"coords": (0.1999, 0.6413), "outcomes": {}, "timeout": 5},
                        "09": {"coords": (0.2976, 0.6552), "outcomes": {}, "timeout": 5},
                        "10": {"coords": (0.4023, 0.6324), "outcomes": {}, "timeout": 5},
                        "11": {"coords": (0.5177, 0.652), "outcomes": {}, "timeout": 5},
                        "12": {"coords": (0.5944, 0.6495), "outcomes": {}, "timeout": 5},
                        "13": {"coords": (0.6836, 0.6618), "outcomes": {}, "timeout": 5},
                        "14": {"coords": (0.7876, 0.652), "outcomes": {}, "timeout": 5},
                    }
                },
                "chaos": {
                    "imagen": "assets/ui/stage-chaos-ep-id.png",
                    "region": (0.7238, 0.2075, 0.757, 0.2484),
                    "botones": {
                        "15": {"coords": (0.4624, 0.5564), "outcomes": {}, "timeout": 5},
                        "16": {"coords": (0.597, 0.5564), "outcomes": {}, "timeout": 5},
                        "17": {"coords": (0.7312, 0.5474), "outcomes": {}, "timeout": 5},
                    }
                }
            },
            "tipo": "chest",
            "valores": {
                "elite-bronze-chest": { # falta el asset de bronze elite chest
                    "region": (0.4956, 0.8047, 0.8333, 0.8848),
                },
                "elite-silver-chest": {
                    "imagen": "assets/ui/elite-silver-chest.png",
                    "region": (0.4956, 0.8047, 0.8333, 0.8848),
                },
                "elite-gold-chest": {
                    "imagen": "assets/ui/elite-gold-chest.png",
                    "region": (0.4956, 0.8047, 0.8333, 0.8848),
                },
                "elite-platinum-chest": {
                    "imagen": "assets/ui/elite-platinum-chest.png",
                    "region": (0.4956, 0.8047, 0.8333, 0.8848),
                },
                "elite-diamond-chest": {
                    "imagen": "assets/ui/elite-diamond-chest.png",
                    "region": (0.4956, 0.8047, 0.8333, 0.8848),
                }
            },
            "tipo": "status",
            "valores": {
                "ready-to-open": {
                    "imagen": "assets/ui/elite-ready-to-open.png",
                    "region": (0.4838, 0.9257, 0.8385, 0.9771),
                },
                "open-with-gold": {
                    "imagen": "assets/ui/elite-open-with-gold.png",
                    "region": (0.4819, 0.9248, 0.778, 0.973),
                },
                "open-with-karats": {
                    "imagen": "assets/ui/elite-open-with-karats.png",
                    "region": (0.4819, 0.9248, 0.778, 0.973),
                }
            }
        },
    },
    "stage-elite-chaos-selected": {
        "imagen": "assets/ui/stage-elite-chaos-selected-id.png",
        "region": (0.1914, 0.2402, 0.2168, 0.3113),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": (0.8009, 0.2802),
            "buff-1": (0.5265, 0.4502),
            "buff-2": (0.5937, 0.4526),
            "buff-3": (0.6674, 0.4412),
            "buff-4": (0.7544, 0.4567),
            "difficulty-1": (0.2371, 0.8619),
            "difficulty-2": (0.3053, 0.8905),
            "difficulty-3": (0.3724, 0.8636),
            "difficulty-4": (0.4458, 0.866),
            "start": (0.7286, 0.8791),
            "x2-start": (0.7098, 0.7778),
            "get-support": (0.743, 0.6814),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "mao-support",
            "valores": {
                "purchased": {
                    "imagen": "assets/ui/mao-purchased-id.png",
                    "region": (0.6515, 0.6299, 0.6906, 0.6838),
                },
                "not-purchased": {
                    "imagen": "assets/ui/mao-not-purchased-id.png",
                    "region": (0.6515, 0.6299, 0.6906, 0.6838),
                },
                "activated": {
                    "imagen": "assets/ui/mao-activated.png",
                    "region": (0.5313, 0.634, 0.6095, 0.6863),
                }
            }
        },

    },
    "stage-elite-chaos-selected-start": {
        "imagen": "assets/ui/stage-elite-chaos-selected-start-id.png",
        "region": (0.4543, 0.4542, 0.6073, 0.4935),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": (0.6615, 0.2132),
            "start": (0.5682, 0.6748),
            "auto-repeat": (0.4318, 0.6789),
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-elite-chaos-in-progress": {
        "imagen": "assets/ui/stage-elite-chaos-in-progress-id.png",
        "region": (0.8573, 0.0359, 0.8979, 0.0752),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "auto-play-toggle": (0.8783, 0.0588),
            "pause": (0.9406, 0.0564),
            "auto-repeat-toggle": (0.5041, 0.7516),
            "EX": (0.6751, 0.8685),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "toggle",
            "valores": {
                "auto-repeat-off": {
                    "imagen": "assets/ui/auto-repeat-toggle-off.png",
                    "region": (0.4336, 0.7173, 0.5656, 0.777),
                },
                "auto-repeat-on": {
                    "imagen": "assets/ui/auto-repeat-toggle-on.png",
                    "region": (0.4432, 0.7222, 0.556, 0.7704),
                },
                "auto-play-off": {
                    "imagen": "assets/ui/auto-play-off.png",
                    "region": (0.8429, 0.018, 0.9115, 0.0915),
                    "threshold": 0.90,
                }
            }
        },
    },
    "stage-elite-chaos-battle-ended": {
        "imagen": "assets/ui/stage-elite-chaos-battle-ended-id.png",
        "region": (0.4373, 0.8252, 0.5619, 0.8766),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "tap": (0.4735, 0.848)
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-elite-chaos-auto-ended": {
        "imagen": "assets/ui/stage-elite-chaos-auto-ended-id.png",
        "region": (0.3514, 0.4363, 0.6486, 0.5049),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": (0.5033, 0.6299),
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-elite-chaos-slot-full": {
        "imagen": "assets/ui/stage-elite-chaos-slot-full-id.png",
        "region": (0.3625, 0.4224, 0.6386, 0.5302),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": (0.4329, 0.6266), # proceed anyway
            "no": (0.5682, 0.6275),  # cancel
        },
        "menus":       {},
        "subcontexto": None
    },
    "stage-elite-chest-rush": {
        "imagen": "assets/ui/stage-elite-chest-rush-id.png",
        "region": (0.3673, 0.7525, 0.4576, 0.8047),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": (0.4329, 0.6675), # use currency
            "no": (0.5697, 0.6708),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "currency",
            "valores": {
                "gold": {
                    "imagen": "assets/ui/rush-with-gold.png",
                    "region": (0.4322, 0.3685, 0.5605, 0.4069),
                },
                "karats": {
                    "imagen": "assets/ui/rush-with-karats.png",
                    "region": (0.4218, 0.3709, 0.5299, 0.4069),
                }
            },
        },
    },
    "stage-paused": {
        "imagen": "assets/ui/paused-id.png",
        "region": (0.4679, 0.2198, 0.5332, 0.268),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": (0.4344, 0.5319), # quit
            "no": (0.5605, 0.5343),  # close
        },
        "menus":       {},
        "subcontexto": None
    },
    "buffs": {
        "imagen": "assets/ui/buffs-id.png",
        "region": (0.4753, 0.0384, 0.5247, 0.0825),
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8182, 0.0588), "outcomes": {}, "timeout": 5},
            "astrologer-buff": {"coords": (0.2813, 0.1658), "outcomes": {}, "timeout": 5},
            "alchemist-buff": {"coords": (0.4414, 0.1585), "outcomes": {}, "timeout": 5},
            "heaven-or-hell": {"coords": (0.6014, 0.1683), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "astrologer-buff-tab": {
                    "imagen": "assets/ui/astrologer-buff-tab.png",
                    "region": (0.274, 0.3505, 0.306, 0.393),
                },
                "alchemist-buff-tab": {
                    "imagen": "assets/ui/alchemist-buff-tab.png",
                    "region": (0.2858, 0.4493, 0.3156, 0.5098),
                    "botones": {
                        "free-buff-video": {"coords": (0.5612, 0.8546), "outcomes": {}, "timeout": 5},
                    }                    
                },
                #"heaven-or-hell-tab": {}, falta completar
            }
        },
    },
    "survival": {
        "imagen": "assets/ui/survival-id.png",
        "region": (0.1707, 0.2337, 0.2994, 0.2974),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1906, 0.0711), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8053, 0.0866), "outcomes": {}, "timeout": 5},
            "monster-wave": {"coords": (0.2389, 0.3995), "outcomes": {}, "timeout": 5},
            "companion-battle": {"coords": (0.4115, 0.4118), "outcomes": {}, "timeout": 5},
            "world-boss": {"coords": (0.3514, 0.7843), "outcomes": {}, "timeout": 5},
            "tot": {"coords": (0.5708, 0.4542), "outcomes": {}, "timeout": 5},
            "tower-of-proof": {"coords": (0.7423, 0.4142), "outcomes": {}, "timeout": 5},
            "labyrinth": {"coords": (0.5763, 0.8039), "outcomes": {}, "timeout": 5},
            "expedition": {"coords": (0.7345, 0.7958), "outcomes": {}, "timeout": 5}
        },
        "menus":       {},
        "subcontexto": None
    },
    "monster-wave": {
        "imagen": "assets/ui/monster-wave-id.png",
        "region": (0.1759, 0.1299, 0.3027, 0.1863),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1785, 0.0523), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8079, 0.0547), "outcomes": {}, "timeout": 5},
            "penance-after-scroll": {"coords": (0.2625, 0.8791), "outcomes": {}, "timeout": 5},
            "buff-1": {"coords": (0.5572, 0.3186), "outcomes": {}, "timeout": 5},
            "buff-2": {"coords": (0.6268, 0.3113), "outcomes": {}, "timeout": 5},
            "buff-3": {"coords": (0.7117, 0.3301), "outcomes": {}, "timeout": 5},
            "buff-4": {"coords": (0.7806, 0.3121), "outcomes": {}, "timeout": 5},
            "skip": {"coords": (0.7636, 0.7092), "outcomes": {}, "timeout": 5},
            "start": {"coords": (0.7651, 0.8734), "outcomes": {}, "timeout": 5},
            "max-sapphires": {"coords": (0.7898, 0.6021), "outcomes": {}, "timeout": 5},
            "x3-sapphires": {"coords": (0.7423, 0.6046), "outcomes": {}, "timeout": 5},
            "x2-sapphires": {"coords": (0.6903, 0.5907), "outcomes": {}, "timeout": 5},
            "x1-sapphires": {"coords": (0.6405, 0.6005), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "difficulty-selected",
            "valores": {
                "penance": {
                    "imagen": "assets/ui/checkmark.png",
                    "region": (0.1947, 0.8162, 0.2474, 0.9052),
                }
            },
        },
    },
    "monster-wave-results": {
        "imagen": "assets/ui/monster-wave-results-id.png",
        "region": (0.3698, 0.4412, 0.5597, 0.4926),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5018, 0.8121), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "monster-wave-skip-confirmation": {
        "imagen": "assets/ui/monster-wave-skip-confirmation-id.png",
        "region": (0.3503, 0.5, 0.6504, 0.5858),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4381, 0.6324), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.58, 0.6209), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": { # COMPLETAR ASSETS
            "tipo": "item-alert",
            "valores": {
                "brawler-full": {
                    "imagen": "",
                    "region": (),
                },
                "weapon-full": {
                    "imagen": "",
                    "region": (),
                },
                "hero-weapon-full": {
                    "imagen": "",
                    "region": (),
                },
                "bronze-full": {
                    "imagen": "",
                    "region": (),
                },
                "silver-full": {
                    "imagen": "",
                    "region": (),
                }
            },
        },
    },
    "monster-wave-points-reward": {
        "imagen": "assets/ui/monster-wave-points-reward-id.png",
        "region": (0.5155, 0.4779, 0.6497, 0.5408),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5015, 0.6585), "outcomes": {}, "timeout": 5}
        },
        "menus":       {},
        "subcontexto": None
    },
    "monster-wave-skip-completed": {
        "imagen": "assets/ui/monster-wave-skip-completed-id.png",
        "region": (0.2662, 0.5842, 0.3156, 0.6528),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4959, 0.759), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "select-boss": {
        "imagen": "assets/ui/select-boss-id.png",
        "region": (0.4524, 0.0547, 0.5468, 0.1021),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "available": {"coords": (0.4974, 0.5449), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.5033, 0.9379), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "world-boss": {
        "imagen": "assets/ui/world-boss-id.png",
        "region": (0.1667, 0.1315, 0.2544, 0.1789),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": {"coords": (0.194, 0.0564), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8156, 0.0564), "outcomes": {}, "timeout": 5},
            "start": {"coords": (0.774, 0.9346), "outcomes": {}, "timeout": 5},
            "auto-repeat": {"coords": (0.7762, 0.8497), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "world-boss-auto-repeat": {
        "imagen": "assets/ui/world-boss-auto-repeat-id.png",
        "region": (0.3282, 0.2737, 0.4133, 0.433),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.6895, 0.1675), "outcomes": {}, "timeout": 5},
            "auto-repeat": {"coords": (0.4897, 0.6127), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "expedition": { # falta completar con los contextos de expedicion completada y en curso
        "imagen": "assets/ui/expedition-id.png",
        "region": (0.2747, 0.3611, 0.3215, 0.4011),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": {"coords": (0.1991, 0.0752), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8042, 0.0882), "outcomes": {}, "timeout": 5},
            "start-expedition": {"coords": (0.6818, 0.9281), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "black-market": {
        "imagen": "assets/ui/black-market-id.png",
        "region": (0.4395, 0.0997, 0.5579, 0.1495),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "buy-item-01": {"coords": (0.4491, 0.3415), "outcomes": {}, "timeout": 5},
            "buy-item-02": {"coords": (0.4506, 0.4698), "outcomes": {}, "timeout": 5},
            "buy-item-03": {"coords": (0.4524, 0.5948), "outcomes": {}, "timeout": 5},
            "buy-item-04": {"coords": (0.4539, 0.7337), "outcomes": {}, "timeout": 5},
            "buy-item-05": {"coords": (0.4454, 0.8725), "outcomes": {}, "timeout": 5},
            "buy-item-06": {"coords": (0.7592, 0.3415), "outcomes": {}, "timeout": 5},
            "buy-item-07": {"coords": (0.757, 0.4706), "outcomes": {}, "timeout": 5},
            "buy-item-08": {"coords": (0.7507, 0.6095), "outcomes": {}, "timeout": 5},
            "buy-item-09": {"coords": (0.7592, 0.7377), "outcomes": {}, "timeout": 5},
            "buy-item-10": {"coords": (0.7592, 0.8717), "outcomes": {}, "timeout": 5},
            "refresh": {"coords": (0.5723, 0.2157), "outcomes": {}, "timeout": 5},
            "close": {"coords": (0.8097, 0.1324), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "currency",
            "valores": {
                "col1": {
                    "imagen": "assets/ui/gold-coin-bm.png",
                    "region": (0.4355, 0.2949, 0.4628, 0.8856),
                },
                "col2": {
                    "imagen": "assets/ui/gold-coin-bm.png",
                    "region": (0.7459, 0.2925, 0.7736, 0.9003),
                }
            },
        },
    },
    "black-market-purchase-confirmation": {
        "imagen": "assets/ui/black-market-purchase-confirmation-id.png",
        "region": (0.4624, 0.4828, 0.5376, 0.5294),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4347, 0.634), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.569, 0.6307), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "season-pass": { # cuando haya evento faltaria agregar su asset
        "imagen": "assets/ui/season-pass-id.png",
        "region": (0.3237, 0.4101, 0.3706, 0.4877),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "race": {"coords": (0.2201, 0.2018), "outcomes": {}, "timeout": 5},
            "growth": {"coords": (0.3127, 0.2222), "outcomes": {}, "timeout": 5},
            "menu-rapido": {"coords": (0.2024, 0.0621), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8009, 0.0842), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "race": {
                    "imagen": "assets/ui/season-pass-race-id.png",
                    "region": (0.3156, 0.4918, 0.3835, 0.576),
                    "botones":   {
                        "claim-all": {"coords": (0.3451, 0.6536), "outcomes": {}, "timeout": 5},
                    },
                }
            }
        },
    },
    "season-pass-claim-all": {
        "imagen": "assets/ui/season-pass-claim-all-id.png",
        "region": (0.4074, 0.4461, 0.5885, 0.5008),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4336, 0.6242), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.569, 0.6258), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "time-rewards": {
        "imagen": "assets/ui/time-rewards-id.png",
        "region": (0.3521, 0.0972, 0.646, 0.165),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8208, 0.1021), "outcomes": {}, "timeout": 5},
            "reward-01": {"coords": (0.285, 0.4755), "outcomes": {}, "timeout": 5},
            "reward-02": {"coords": (0.5044, 0.4706), "outcomes": {}, "timeout": 5},
            "reward-03": {"coords": (0.7058, 0.4706), "outcomes": {}, "timeout": 5},
            "reward-04": {"coords": (0.2902, 0.7745), "outcomes": {}, "timeout": 5},
            "reward-05": {"coords": (0.5026, 0.7639), "outcomes": {}, "timeout": 5},
            "reward-06": {"coords": (0.715, 0.7614), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "reward",
            "valores": {
                "ready": {
                    "imagen": "assets/ui/claim-reward.png", # aca hay que buscar todas las ocurrencias
                    "region": (0.2271, 0.4314, 0.774, 0.8007),
                }
            }
        },
    },
    "battle": {
        "imagen": "assets/ui/battle-id.png",
        "region": (0.2456, 0.2443, 0.3119, 0.3015),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "arena": {"coords": (0.2847, 0.424), "outcomes": {}, "timeout": 5},
            "league-match": {"coords": (0.4908, 0.3685), "outcomes": {}, "timeout": 5},
            "invasion": {"coords": (0.2872, 0.7426), "outcomes": {}, "timeout": 5},
            "ranker-break": {"coords": (0.4779, 0.7288), "outcomes": {}, "timeout": 5},
            "melee": {"coords": (0.7286, 0.7165), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8013, 0.0743), "outcomes": {}, "timeout": 5},
            "menu-rapido": {"coords": (0.205, 0.0564), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "arena": {
        "imagen": "assets/ui/arena-id.png",
        "region": (0.1641, 0.2247, 0.2227, 0.2835),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1914, 0.0678), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8001, 0.0858), "outcomes": {}, "timeout": 5},
            "beginner": {"coords": (0.2806, 0.6479), "outcomes": {}, "timeout": 5},
            "intermediate": {"coords": (0.483, 0.5727), "outcomes": {}, "timeout": 5},
            "expert": {"coords": (0.7459, 0.585), "outcomes": {}, "timeout": 5},
            "refresh": {"coords": (0.7688, 0.9461), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "arena-selected": {
        "imagen": "assets/ui/arena-id.png",
        "region": (0.1667, 0.1454, 0.2271, 0.2002),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "x2": {"coords": (0.6615, 0.7312), "outcomes": {}, "timeout": 5},
            "x3": {"coords": (0.7076, 0.7312), "outcomes": {}, "timeout": 5},
            "x5": {"coords": (0.743, 0.7361), "outcomes": {}, "timeout": 5},
            "x8": {"coords": (0.7902, 0.7304), "outcomes": {}, "timeout": 5},
            "buff-1": {"coords": (0.5509, 0.3758), "outcomes": {}, "timeout": 5},
            "buff-2": {"coords": (0.6763, 0.3619), "outcomes": {}, "timeout": 5},
            "buff-3": {"coords": (0.7681, 0.3603), "outcomes": {}, "timeout": 5},
            "menu-rapido": {"coords": (0.194, 0.0703), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.7968, 0.0645), "outcomes": {}, "timeout": 5},
            "start": {"coords": (0.7677, 0.9534), "outcomes": {}, "timeout": 5},
            "auto-repeat": {"coords": (0.7603, 0.8521), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "selected",
            "valores": {
                "buff-1": {
                    "imagen": "assets/ui/buff-1-arena-selected.png",
                    "region": (0.5059, 0.2304, 0.5542, 0.3292),
                },
                "buff-2": {
                    "imagen": "assets/ui/buff-2-arena-selected.png",
                    "region": (0.6114, 0.2247, 0.6659, 0.3301),
                },
                "buff-3": {
                    "imagen": "assets/ui/buff-3-arena-selected.png",
                    "region": (0.7187, 0.232, 0.7688, 0.3276),
                },
                "x8-selected": {
                    "imagen": "assets/ui/x8-arena-selected.png",
                    "region": (0.7644, 0.6708, 0.8086, 0.7745),
                },
            }
        },
    },
    "arena-selected-auto": {
        "imagen": "assets/ui/arena-selected-auto-id.png",
        "region": (0.3267, 0.1781, 0.4174, 0.2737),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.6847, 0.1021), "outcomes": {}, "timeout": 5},
            "auto-repeat": {"coords": (0.5052, 0.8799), "outcomes": {}, "timeout": 5},
            "upon-defeat": {"coords": (0.6608, 0.7721), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "checkbox",
            "valores": {
                "upon-defeat": {
                    "imagen": "assets/ui/checkbox-marked.png",
                    "region": (0.649, 0.7255, 0.6759, 0.7917),
                },
            }
        },
    },
    "arena-battle-ended": {
        "imagen": "assets/ui/arena-battle-ended-id.png",
        "region": (0.4344, 0.8521, 0.5645, 0.9093),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "tap": {"coords": (0.4875, 0.8889), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "arena-auto-repeat-defeated": {
        "imagen": "assets/ui/arena-auto-repeat-defeated-id.png",
        "region": (0.3514, 0.4297, 0.6479, 0.5147),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4934, 0.6291), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "arena-battle-in-progress": {
        "imagen": "assets/ui/arena-battle-in-progress-id.png",
        "region": (0.4771, 0.0392, 0.5221, 0.1095),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "pause": {"coords": (0.8182, 0.183), "outcomes": {}, "timeout": 5},
            "auto-repeat": {"coords": (0.5018, 0.7525), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "toggle",
            "valores": {
                "auto-repeat-off": {
                    "imagen": "assets/ui/auto-repeat-toggle-off.png",
                    "region": (0.4336, 0.7173, 0.5656, 0.777),
                },
                "auto-repeat-on": {
                    "imagen": "assets/ui/auto-repeat-toggle-on.png",
                    "region": (0.4432, 0.7222, 0.556, 0.7704),
                }
            }
        },
    },
    "arena-tryouts-complete": {
        "imagen": "assets/ui/arena-tryouts-complete-id.png",
        "region": (0.4141, 0.2525, 0.5848, 0.3194),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4941, 0.7288), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "arena-points-reward": {
        "imagen": "assets/ui/arena-points-reward-id.png",
        "region": (0.4355, 0.2165, 0.5631, 0.2745),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4993, 0.6683), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "mailbox": {
        "imagen": "assets/ui/mailbox-id.png",
        "region": (0.4738, 0.1413, 0.5402, 0.1895),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8197, 0.1675), "outcomes": {}, "timeout": 5},
            "account-mail": {"coords": (0.2618, 0.2786), "outcomes": {}, "timeout": 5},
            "character-mail": {"coords": (0.382, 0.2778), "outcomes": {}, "timeout": 5},
            #"striker-rewards": (0.5077, 0.2884), # no real use cases
            "friends": {"coords": (0.6235, 0.2827), "outcomes": {}, "timeout": 5},
            "claim-all": {"coords": (0.4764, 0.3546), "outcomes": {}, "timeout": 5},
            "delete-read": {"coords": (0.2898, 0.357), "outcomes": {}, "timeout": 5},
            "claim-pos1": {"coords": (0.7493, 0.4575), "outcomes": {}, "timeout": 5},
            "claim-pos2": {"coords": (0.7485, 0.576), "outcomes": {}, "timeout": 5},
            "claim-pos3": {"coords": (0.7474, 0.7002), "outcomes": {}, "timeout": 5},
            "claim-pos4": {"coords": (0.7485, 0.8121), "outcomes": {}, "timeout": 5},
            "claim-bottom-after-scroll": {"coords": (0.7482, 0.8636), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "account-mail": {
                    "imagen": "assets/ui/mailbox-account-mail-tab.png",
                    "region": (0.1888, 0.2222, 0.3171, 0.3178),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                },
                "character-mail": {
                    "imagen": "assets/ui/mailbox-character-mail-tab.png",
                    "region": (0.3178, 0.2222, 0.4432, 0.3162),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                },
                #"striker-rewards": {  # no real use cases
                #    "imagen": ,
                #    "region": ,
                #    "threshold": 0.9
                #},
                "friends": {
                    "imagen": "assets/ui/mailbox-friends-tab.png",
                    "region": (0.5737, 0.223, 0.6987, 0.3178),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                }
            },
            "tipo": "state",
            "valores": {
                "no-mail": {
                    "imagen": "assets/ui/mailbox-no-mail.png",
                    "region": (0.4038, 0.5662, 0.5892, 0.6201),
                }
            }
        },
    },
    "friends": {
        "imagen": "assets/ui/friends-id.png",
        "region": (0.4668, 0.0694, 0.5339, 0.1185),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8127, 0.107), "outcomes": {}, "timeout": 5},
            "send-res-to-all": {"coords": (0.7662, 0.8889), "outcomes": {}, "timeout": 5},
            "delete": {"coords": (0.5597, 0.8954), "outcomes": {}, "timeout": 5},
            "list": {"coords": (0.2364, 0.2083), "outcomes": {}, "timeout": 5},
            "recommended": {"coords": (0.3418, 0.2181), "outcomes": {}, "timeout": 5},
            "pending": {"coords": (0.4458, 0.2165), "outcomes": {}, "timeout": 5},
            "page-down": {"coords": (0.3879, 0.924), "outcomes": {}, "timeout": 5},
            "page-up": {"coords": (0.2935, 0.9232), "outcomes": {}, "timeout": 5},
            "slot-1": {"coords": (0.4473, 0.3636), "outcomes": {}, "timeout": 5},
            "slot-2": {"coords": (0.4458, 0.5082), "outcomes": {}, "timeout": 5},
            "slot-3": {"coords": (0.4458, 0.6454), "outcomes": {}, "timeout": 5},
            "slot-4": {"coords": (0.448, 0.8031), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "list": {
                    "imagen": "assets/ui/friends-list-tab-id.png",
                    "region": (0.5313, 0.8725, 0.5815, 0.9158),
                },
                "recommended": {
                    "imagen": "assets/ui/friends-recommended-tab-id.png",
                    "region": (0.5347, 0.8603, 0.5885, 0.9142),
                },
                "pending": {
                    "imagen": "assets/ui/friends-pending-tab-id.png",
                    "region": (0.535, 0.875, 0.5793, 0.9216),
                }
            }
        },
    },
    "friends-delete": {
        "imagen": "assets/ui/friends-delete-id.png",
        "region": (0.3879, 0.4796, 0.6139, 0.5319),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4347, 0.6364), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.5737, 0.6283), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "friends-pending-max-amount": {
        "imagen": "assets/ui/friends-pending-max-amount-id.png",
        "region": (0.4259, 0.469, 0.5841, 0.5098),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5015, 0.6283), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "friends-recommended-request-sent": {
        "imagen": "assets/ui/friends-recommended-request-sent-id.png",
        "region": (0.3979, 0.4485, 0.604, 0.4992),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4967, 0.6422), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "quests": { # de momento funcional, se pueden agregar cosas
        "imagen": "assets/ui/quests-id.png",
        "region": (0.4676, 0.0703, 0.5313, 0.125),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8256, 0.0948), "outcomes": {}, "timeout": 5},
            "claim-all": {"coords": (0.6973, 0.1364), "outcomes": {}, "timeout": 5},
            "claim-karat": {"coords": (0.6921, 0.3292), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "daily-quests": {
                    "imagen": "assets/ui/quests-daily-tab-id.png",
                    "region": (0.2312, 0.2745, 0.2677, 0.3734),
                }
            }
        },
    },
    "bag-full-alert": { # creo que es bag de socket full, revisar si es siempre igual
        "imagen": "assets/ui/bag-full-alert-id.png",
        "region": (0.4513, 0.4338, 0.5487, 0.4804),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4395, 0.6332), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.5697, 0.6291), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "tot": { # Tower of Tribulations
        "imagen":                 "assets/ui/tot-id.png",
        "region":                 (175, 152, 392, 187),
        "threshold":              0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "back":           {"coords": (851, 32), "outcomes": {}, "timeout": 5},
            "menu-rapido":    {"coords": (134, 41), "outcomes": {}, "timeout": 5},
            "physical-tower": {"coords": (189, 130), "outcomes": {}, "timeout": 5},
            "magical-tower":  {"coords": (366, 134), "outcomes": {}, "timeout": 5},
            "socket":         {"coords": (810, 313), "outcomes": {}, "timeout": 5},
            "start":          {"coords": (806, 522), "outcomes": {}, "timeout": 5},
            "auto-repeat":    {"coords": (808, 480), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": {
            "tipo": "tower",
            "valores": {
                "physical": {
                    "imagen":    "assets/ui/physical-tower-id.png",
                    "region":    (118, 216, 447, 449),
                    "threshold": 0.7,
                    "botones":   {},
                },
                "magical": {
                    "imagen":    "assets/ui/magical-tower-id.png",
                    "region":    (126, 229, 443, 469),
                    "threshold": 0.7,
                    "botones":   {},
                },
            }
        },
    },
    "tot-auto-repeat": {
        "imagen": "assets/ui/tot-auto-repeat-id.png",
        "region": (478, 126, 842, 246),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo":       None,
        "botones": {
            "auto-repeat": {"coords": (562, 399), "outcomes": {}, "timeout": 5},
            "auto-continue": {"coords": (743, 388), "outcomes": {}, "timeout": 5},
            "close": {"coords": (854, 83), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "tot-auto-repeat-defeated": {
        "imagen": "assets/ui/tot-auto-repeat-defeated-id.png",
        "region": (299, 209, 658, 297),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo":       None,
        "botones": {
            "ok": {"coords": (486, 335), "outcomes": {}, "timeout": 5}
        },
        "menus":       {},
        "subcontexto": None
    },
    "tot-auto-repeat-end": {
        "imagen": "assets/ui/tot-auto-repeat-end-id.png",
        "region": (299, 209, 658, 297),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo":       None,
        "botones": {
            "ok": {"coords": (477, 338), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "socket": {
        "imagen": "assets/ui/socket-id.png",
        "region": (0.5424, 0.9044, 0.6685, 0.9779),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1999, 0.0743), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8009, 0.0768), "outcomes": {}, "timeout": 5},
            "socket": {"coords": (0.1987, 0.1904), "outcomes": {}, "timeout": 5},
            "equipment-home": {"coords": (0.3131, 0.1838), "outcomes": {}, "timeout": 5},
            "enhance-gem-absorption": {"coords": (0.4277, 0.1855), "outcomes": {}, "timeout": 5},
            "enhance-all": {"coords": (0.6206, 0.9534), "outcomes": {}, "timeout": 5},
            "next-page": {"coords": (0.7987, 0.9461), "outcomes": {}, "timeout": 5},
            "prev-page": {"coords": (0.7043, 0.942), "outcomes": {}, "timeout": 5},
            "bag-slot-01": {"coords": (0.5808, 0.402), "outcomes": {}, "timeout": 5},
            "bag-slot-02": {"coords": (0.6504, 0.4109), "outcomes": {}, "timeout": 5},
            "bag-slot-03": {"coords": (0.7124, 0.406), "outcomes": {}, "timeout": 5},
            "bag-slot-04": {"coords": (0.7858, 0.3995), "outcomes": {}, "timeout": 5},
            "bag-slot-05": {"coords": (0.5848, 0.5408), "outcomes": {}, "timeout": 5},
            "bag-slot-06": {"coords": (0.6486, 0.5498), "outcomes": {}, "timeout": 5},
            "bag-slot-07": {"coords": (0.7187, 0.54), "outcomes": {}, "timeout": 5},
            "bag-slot-08": {"coords": (0.7876, 0.5425), "outcomes": {}, "timeout": 5},
            "bag-slot-09": {"coords": (0.5826, 0.6781), "outcomes": {}, "timeout": 5},
            "bag-slot-10": {"coords": (0.6512, 0.6748), "outcomes": {}, "timeout": 5},
            "bag-slot-11": {"coords": (0.7201, 0.6895), "outcomes": {}, "timeout": 5},
            "bag-slot-12": {"coords": (0.7788, 0.6944), "outcomes": {}, "timeout": 5},
            "bag-slot-13": {"coords": (0.5808, 0.817), "outcomes": {}, "timeout": 5},
            "bag-slot-14": {"coords": (0.6538, 0.8186), "outcomes": {}, "timeout": 5},
            "bag-slot-15": {"coords": (0.7153, 0.8219), "outcomes": {}, "timeout": 5},
            "bag-slot-16": {"coords": (0.7847, 0.8211), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "socket": {
                    "imagen": "assets/ui/socket-tab-id.png",
                    "region": (0.1718, 0.2369, 0.2585, 0.2712),
                },
                "equipment-home": {
                    "imagen": "assets/ui/equipment-home-tab-id.png",
                    "region": (0.1869, 0.2443, 0.2688, 0.2721),
                }
            }
        },
    },
    "socket-enhance-all": {
        "imagen": "assets/ui/socket-enhance-all-id.png",
        "region": (0.4591, 0.1716, 0.5435, 0.2157),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.7482, 0.1601), "outcomes": {}, "timeout": 5},
            "gold-enhance": {"coords": (0.3875, 0.8382), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "socket-enhance-all-no-material": {
        "imagen": "assets/ui/socket-enhance-all-no-material-id.png",
        "region": (0.4336, 0.4436, 0.5664, 0.5008),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4934, 0.634), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "socket-sell-opal": {
        "imagen": "assets/ui/socket-sell-opal-id.png",
        "region": (0.3599, 0.6013, 0.4403, 0.6569),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "sell-bulk": {"coords": (0.4004, 0.6332), "outcomes": {}, "timeout": 5},
            "sell": {"coords": (0.4967, 0.6258), "outcomes": {}, "timeout": 5},
            "cancel": {"coords": (0.5985, 0.6364), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "trading-center": {
        "imagen": "assets/ui/trading-center-id.png",
        "region": (0.2902, 0.1046, 0.4133, 0.165),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.7813, 0.1511), "outcomes": {}, "timeout": 5},
            "general": {"coords": (0.2924, 0.2418), "outcomes": {}, "timeout": 5},
            #"pets": (0.3861, 0.2484),           # no real use cases
            "avatar-and-keys": {"coords": (0.4753, 0.25), "outcomes": {}, "timeout": 5},
            "currency": {"coords": (0.5815, 0.2418), "outcomes": {}, "timeout": 5},
            #"special-currency": (0.6881, 0.25), # no real use cases
            "events": {"coords": (0.1873, 0.2786), "outcomes": {}, "timeout": 5},
            #"premium-coins": (0.1869, 0.3856),  # no real use cases
            "trade-slot-1": {"coords": (0.7091, 0.4297), "outcomes": {}, "timeout": 5},
            "trade-slot-2": {"coords": (0.7076, 0.5727), "outcomes": {}, "timeout": 5},
            "trade-slot-3": {"coords": (0.7065, 0.7214), "outcomes": {}, "timeout": 5},
            "trade-slot-4": {"coords": (0.7098, 0.8824), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "general": {
                    "imagen": "assets/ui/trading-center-general-tab-id.png",
                    "region": (0.2356, 0.1928, 0.3333, 0.2859),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                    
                },
                "avatar-and-keys": {
                    "imagen": "assets/ui/trading-center-avatar-and-keys-tab-id.png",
                    "region": (0.4388, 0.1969, 0.5339, 0.29),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                },
                "currency": {
                    "imagen": "assets/ui/trading-center-currency-tab-id.png",
                    "region": (0.5383, 0.1936, 0.6346, 0.2859),
                    "threshold": 0.9 # mas alto porque compara en escala de grises
                },
                #"special-currency": { # no real use cases
                #    "threshold": 0.9 # mas alto porque compara en escala de grises
                #}
            }
        },
    },
    "trading-center-max-gold-pouch": {
        "imagen": "assets/ui/trading-center-max-gold-pouch-id.png",
        "region": (0.3639, 0.4338, 0.6327, 0.5196),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5026, 0.6307), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "trading-center-item-trade": {
        "imagen": "assets/ui/trading-center-item-trade-id.png",
        "region": (0.4583, 0.1855, 0.545, 0.2369),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "no": {"coords": (0.3599, 0.7778), "outcomes": {}, "timeout": 5},
            "trade": {"coords": (0.5026, 0.7778), "outcomes": {}, "timeout": 5},
            "max-available-trades": {"coords": (0.7043, 0.8137), "outcomes": {}, "timeout": 5},
            "plus-one-available-trade": {"coords": (0.6685, 0.8056), "outcomes": {}, "timeout": 5},
            "minus-one-available-trade": {"coords": (0.5848, 0.8007), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "trading-center-item-trade-exception": {
        "imagen": "assets/ui/trading-center-item-trade-exception-id.png",
        "region": (0.3639, 0.4322, 0.6368, 0.5155),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5044, 0.6258), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "trading-center-insufficient-items": {
        "imagen": "assets/ui/trading-center-insufficient-items-id.png",
        "region": (0.4082, 0.4297, 0.5918, 0.5139),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.5007, 0.6299), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None
    },
    "craft": {
        "imagen": "assets/ui/craft-id.png",
        "region": (0.4233, 0.4869, 0.4993, 0.5278),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1973, 0.0498), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.8027, 0.0662), "outcomes": {}, "timeout": 5},
            "weapon-hero-craft": {"coords": (0.823, 0.3562), "outcomes": {}, "timeout": 5},
            "armor-hero-craft": {"coords": (0.8241, 0.6234), "outcomes": {}, "timeout": 5},
            "accessories-hero-craft": {"coords": (0.8249, 0.8954), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None,
    },
    "craft-amount": {
        "imagen": "assets/ui/craft-amount-id.png",
        "region": (0.3263, 0.7132, 0.3827, 0.7974),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "cancel": {"coords": (0.6184, 0.652), "outcomes": {}, "timeout": 5},
            "craft": {"coords": (0.4679, 0.6552), "outcomes": {}, "timeout": 5},
            "max-amount": {"coords": (0.5483, 0.7688), "outcomes": {}, "timeout": 5},
            "plus-one-amount": {"coords": (0.5118, 0.7565), "outcomes": {}, "timeout": 5},
            "minus-one-amount": {"coords": (0.4233, 0.7574), "outcomes": {}, "timeout": 5},
            "slot-3": {"coords": (0.4948, 0.4158), "outcomes": {}, "timeout": 5},
            "slot-2": {"coords": (0.4115, 0.4208), "outcomes": {}, "timeout": 5},
            "slot-1": {"coords": (0.3215, 0.4314), "outcomes": {}, "timeout": 5},
            "slot-4": {"coords": (0.5878, 0.4289), "outcomes": {}, "timeout": 5},
            "slot-5": {"coords": (0.677, 0.4338), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "selected",
            "valores": {
                "slot-1": {
                    "imagen": "assets/ui/craft-amount-selected.png",
                    "region": (0.34, 0.2484, 0.3776, 0.3301),
                },
                "slot-2": {
                    "imagen": "assets/ui/craft-amount-selected.png",
                    "region": (0.4237, 0.25, 0.4591, 0.3325),
                },
                "slot-3": {
                    "imagen": "assets/ui/craft-amount-selected.png",
                    "region": (0.5044, 0.2451, 0.545, 0.3391),
                },
                "slot-4": {
                    "imagen": "assets/ui/craft-amount-selected.png",
                    "region": (0.5859, 0.2451, 0.6316, 0.3448),
                },
                "slot-5": {
                    "imagen": "assets/ui/craft-amount-selected.png",
                    "region": (0.6711, 0.2402, 0.7161, 0.348),
                }
            }
        },
    },
    "craft-amount-exception": {
        "imagen": "assets/ui/craft-amount-exception-id.png",
        "region": (0.3625, 0.4346, 0.6361, 0.5114),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "ok": {"coords": (0.4982, 0.6275), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": None,
    },
    "meteorites": { # no veo una forma consistente de reconocer este contexto porque la barra de titulo puede ser tapada por el chat, uso la de subcontexto
        "imagen": "assets/ui/meteorites-id.png",
        "region": (0.7124, 0.2345, 0.8086, 0.2794),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": {"coords": (0.1932, 0.0792), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.7994, 0.0752), "outcomes": {}, "timeout": 5},
            "meteorites-tab": {"coords": (0.2124, 0.1822), "outcomes": {}, "timeout": 5},
            "combine-tab": {"coords": (0.2957, 0.1822), "outcomes": {}, "timeout": 5},
            "evolve-tab": {"coords": (0.3802, 0.1846), "outcomes": {}, "timeout": 5},
            "bag-slot-01": {"coords": (0.5874, 0.3791), "outcomes": {}, "timeout": 5},
            "bag-slot-02": {"coords": (0.6497, 0.375), "outcomes": {}, "timeout": 5},
            "bag-slot-03": {"coords": (0.7142, 0.3701), "outcomes": {}, "timeout": 5},
            "bag-slot-04": {"coords": (0.7813, 0.3766), "outcomes": {}, "timeout": 5},
            "bag-slot-05": {"coords": (0.5756, 0.5098), "outcomes": {}, "timeout": 5},
            "bag-slot-06": {"coords": (0.6453, 0.518), "outcomes": {}, "timeout": 5},
            "bag-slot-07": {"coords": (0.7124, 0.5074), "outcomes": {}, "timeout": 5},
            "bag-slot-08": {"coords": (0.7865, 0.5204), "outcomes": {}, "timeout": 5},
            "bag-slot-09": {"coords": (0.5704, 0.652), "outcomes": {}, "timeout": 5},
            "bag-slot-10": {"coords": (0.6464, 0.6552), "outcomes": {}, "timeout": 5},
            "bag-slot-11": {"coords": (0.7176, 0.6552), "outcomes": {}, "timeout": 5},
            "bag-slot-12": {"coords": (0.7865, 0.6389), "outcomes": {}, "timeout": 5},
            "bag-slot-13": {"coords": (0.5808, 0.7794), "outcomes": {}, "timeout": 5},
            "bag-slot-14": {"coords": (0.6471, 0.7949), "outcomes": {}, "timeout": 5},
            "bag-slot-15": {"coords": (0.7098, 0.7802), "outcomes": {}, "timeout": 5},
            "bag-slot-16": {"coords": (0.7847, 0.7958), "outcomes": {}, "timeout": 5},
            "next-page": {"coords": (0.7319, 0.9142), "outcomes": {}, "timeout": 5},
            "prev-page": {"coords": (0.6431, 0.9175), "outcomes": {}, "timeout": 5},

            
        },
        "menus": {
            "current-meteorite": {
                "imagen": "assets/ui/current-meteorite-id.png",
                "region": (0.2017, 0.4069, 0.2382, 0.491),
                "botones": {
                    "equip-unequip": {"coords": (0.2161, 0.3178), "outcomes": {}, "timeout": 5},
                    "enhance": {"coords": (0.2227, 0.4477), "outcomes": {}, "timeout": 5},
                    "reforge-evolve": {"coords": (0.2201, 0.6021), "outcomes": {}, "timeout": 5},
                    "reroll-reforge": {"coords": (0.2209, 0.7386), "outcomes": {}, "timeout": 5},
                }
            }
        },
        "subcontexto": {
            "tipo": "set",
            "valores": {
                "1": {
                    "imagen": "assets/ui/meteorites-set1-id.png",
                    "region": (0.1822, 0.2296, 0.2161, 0.2974),
                },
                "2": {
                    "imagen": "assets/ui/meteorites-set2-id.png",
                    "region": (0.2356, 0.2345, 0.267, 0.2949),
                }
            },
            "tipo": "tab",
            "valores": {
                "meteorites": {
                    "imagen": "assets/ui/meteorites-id.png",
                    "region": (0.7124, 0.2345, 0.8086, 0.2794),
                    "botones": {
                        "set-1": {"coords": (0.2176, 0.2778), "outcomes": {}, "timeout": 5},
                        "set-2": {"coords": (0.2681, 0.2843), "outcomes": {}, "timeout": 5},
                        "set-3": {"coords": (0.3208, 0.277), "outcomes": {}, "timeout": 5},
                        "slot-01": {"coords": (0.226, 0.3971), "outcomes": {}, "timeout": 5},
                        "slot-02": {"coords": (0.306, 0.4044), "outcomes": {}, "timeout": 5},
                        "slot-03": {"coords": (0.3894, 0.4044), "outcomes": {}, "timeout": 5},
                        "slot-04": {"coords": (0.4712, 0.4142), "outcomes": {}, "timeout": 5},
                        "slot-05": {"coords": (0.2485, 0.6152), "outcomes": {}, "timeout": 5},
                        "slot-06": {"coords": (0.4491, 0.616), "outcomes": {}, "timeout": 5},
                        "slot-07": {"coords": (0.226, 0.8096), "outcomes": {}, "timeout": 5},
                        "slot-08": {"coords": (0.3097, 0.8072), "outcomes": {}, "timeout": 5},
                        "slot-09": {"coords": (0.3905, 0.8096), "outcomes": {}, "timeout": 5},
                        "slot-10": {"coords": (0.4676, 0.8162), "outcomes": {}, "timeout": 5},
                        "slot-00": {"coords": (0.3485, 0.6062), "outcomes": {}, "timeout": 5},
                    }
                },
                # completar mas tabs para manejo de stock, de momento sirve para cambios de set
            },
            "tipo": "state",
            "valores": {
                "slot-empty": {
                    "imagen": "assets/ui/meteorite-slot-empty.png",
                    "region": (0.1888, 0.3211, 0.5092, 0.8848),
                },
                "flare-empty": {
                    "imagen": "assets/ui/flare-empty.png",
                    "region": (0.3274, 0.5801, 0.3698, 0.6348),
                }
            }
        },
    },
    "combine": {
        "imagen": "assets/ui/combine-id.png",
        "region": (0.5409, 0.8799, 0.6563, 0.9526),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": {"coords": (0.2013, 0.0743), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.7917, 0.0866), "outcomes": {}, "timeout": 5},
            "fuse": {"coords": (0.2179, 0.1879), "outcomes": {}, "timeout": 5},
            "transmute": {"coords": (0.3086, 0.1912), "outcomes": {}, "timeout": 5},
            "combine-all": {"coords": (0.6073, 0.9297), "outcomes": {}, "timeout": 5},
            "ethereal-transmute": {"coords": (0.351, 0.9257), "outcomes": {}, "timeout": 5},
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "fuse": {
                    "imagen": "assets/ui/combine-fuse-tab.png",
                    "region": (0.3459, 0.4069, 0.3931, 0.4592),
                },
                "transmute": {
                    "imagen": "assets/ui/combine-transmute-tab.png",
                    "region": (0.3632, 0.4069, 0.4668, 0.4616),
                }
            }
        },
    },
    "combine-all-higher": {
        "imagen": "assets/ui/combine-all-higher-id.png",
        "region": (0.5162, 0.2361, 0.5619, 0.277),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "combine-all": {"coords": (0.4543, 0.7092), "outcomes": {}, "timeout": 5},
            "cancel": {"coords": (0.5782, 0.7206), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": None
    },
    "combine-all-identical": {
        "imagen": "assets/ui/combine-all-identical-id.png",
        "region": (0.5111, 0.2345, 0.5704, 0.2745),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "combine-all": {"coords": (0.4543, 0.7092), "outcomes": {}, "timeout": 5},
            "cancel": {"coords": (0.5782, 0.7206), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": None
    },
    "inventory": {
        "imagen": "assets/ui/inventory-id.png",
        "region": (0.2507, 0.643, 0.2902, 0.7369),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": {"coords": (0.2006, 0.0776), "outcomes": {}, "timeout": 5},
            "back": {"coords": (0.7917, 0.0792), "outcomes": {}, "timeout": 5},
            "auto-equip": {"coords": (0.6132, 0.9183), "outcomes": {}, "timeout": 5},
            "next-page": {"coords": (0.8042, 0.9158), "outcomes": {}, "timeout": 5},
            "prev-page": {"coords": (0.7124, 0.9158), "outcomes": {}, "timeout": 5}
        },
        "menus": {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "fuse": {
                    "imagen": "assets/ui/combine-fuse-tab.png",
                    "region": (0.3459, 0.4069, 0.3931, 0.4592),
                },
                "transmute": {
                    "imagen": "assets/ui/combine-transmute-tab.png",
                    "region": (0.3632, 0.4069, 0.4668, 0.4616),
                }
            }, # faltan los contextos necesarios para comprar espacio de inventario
            "tipo": "item-lock",
            "valores": {
                "slot1": {
                    "imagen": "assets/ui/inventory-unlock.png",
                    "region": (0.5951, 0.3252, 0.6386, 0.4257),
                    "botones": {
                        "unlock1": {"coords": (0.6515, 0.3815), "outcomes": {}, "timeout": 5},
                    }
                },
                "slot2": {
                    "imagen": "assets/ui/inventory-unlock.png",
                    "region": (0.59, 0.4575, 0.6431, 0.5678),
                    "botones": {
                        "unlock2": {"coords": (0.6589, 0.5139), "outcomes": {}, "timeout": 5},
                    }
                },
                "slot3": {
                    "imagen": "assets/ui/inventory-unlock.png",
                    "region": (0.5918, 0.6005, 0.6405, 0.7026),
                    "botones": {
                        "unlock3": {"coords": (0.6523, 0.6585), "outcomes": {}, "timeout": 5},
                    }
                },
                "slot4": {
                    "imagen": "assets/ui/inventory-unlock.png",
                    "region": (0.5878, 0.732, 0.6412, 0.8448),
                    "botones": {
                        "unlock4": {"coords": (0.6667, 0.7908), "outcomes": {}, "timeout": 5},
                    }
                }
            },
        },
    },
    "awakening": { # notar que cuando pones receive-rewards te manda a ultimate
        "imagen": "assets/ui/awakening-id.png",
        "region": (0.2017, 0.1315, 0.3046, 0.1846),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "close": {"coords": (0.8138, 0.116), "outcomes": {}, "timeout": 5},
            "awaken": {"coords": (0.2541, 0.0752), "outcomes": {}, "timeout": 5},
            "super-awaken": {"coords": (0.3418, 0.0654), "outcomes": {}, "timeout": 5},
            "ultimate-awakening": {"coords": (0.4403, 0.0703), "outcomes": {}, "timeout": 5},
            "complete-all": {"coords": (0.4373, 0.1658), "outcomes": {}, "timeout": 5},
            "receive-rewards": {"coords": (0.6283, 0.259), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "awaken": {
                    "imagen": "assets/ui/awaken-tab.png",
                    "region": (0.7043, 0.1961, 0.7441, 0.2892),
                },
                "super-awaken": {
                    "imagen": "assets/ui/super-awaken-tab.png",
                    "region": (0.7043, 0.1912, 0.7441, 0.2933),
                },
                "ultimate-awakening": {
                    "imagen": "assets/ui/ultimate-awakening-tab.png",
                    "region": (0.7058, 0.1928, 0.7456, 0.2982),
                },
            },
            "tipo": "status",
            "valores": {
                "done": {
                    "imagen": "assets/ui/awakening-status-done.png",
                    "region": (0.5996, 0.3725, 0.6759, 0.4755),
                },
                "not-ready": {
                    "imagen": "assets/ui/awakening-not-ready.png",
                    "region": (0.3237, 0.2206, 0.4115, 0.259),
                }
            },
        },
    },
    "awakening-receive-rewards-alert": {
        "imagen": "assets/ui/awakening-receive-rewards-alert-id.png",
        "region": (0.4004, 0.4044, 0.597, 0.4461),
        "threshold": 0.85,
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "yes": {"coords": (0.4355, 0.634), "outcomes": {}, "timeout": 5},
            "no": {"coords": (0.5756, 0.6185), "outcomes": {}, "timeout": 5},
        },
        "menus": {},
        "subcontexto": None,
    },
    "treasure": {
        "imagen": "assets/ui/treasure-id.png",
        "region": (0.4355, 0.6863, 0.4805, 0.7835),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo": "default",
        "botones": {
            "menu-rapido": (0.1958, 0.0752),
            "back": (0.8042, 0.0801),
            "bronze-chest": (0.4465, 0.3137),
            "silver-chest": (0.5553, 0.3342),
            "gold-chest": (0.6574, 0.3325),
            "platinum-chest": (0.7644, 0.3513),
            "gem-bronze-chest": (0.4524, 0.7132),
            "gem-silver-chest": (0.552, 0.7239),
            "gem-gold-chest": (0.6589, 0.7402),
            "gem-opal-chest": (0.7644, 0.7288),
        },
        "menus": {
            "gold-chest-menu": {
                "imagen": "assets/ui/trasure-menu-opened.png", # mismo para todos los chest
                "region": (0.1855, 0.2002, 0.2909, 0.241),     # mismo para todos los chest
                "botones": {
                    "open-1": (0.6206, 0.482),
                    "open-10-or-max": (0.6965, 0.4837),
                    "close-menu": (0.6667, 0.3513),
                }
            },
            "platinum-chest-menu": {
                "imagen": "assets/ui/trasure-menu-opened.png", # mismo para todos los chest
                "region": (0.1855, 0.2002, 0.2909, 0.241),     # mismo para todos los chest
                "botones": {
                    "open-1": (0.7541, 0.4951),
                    "open-10-or-max": (0.8282, 0.4959),
                    "close-menu": (0.7618, 0.3611),
                },
                # completar demas menus
            }
        },
        "subcontexto": None,
    },
    "opening-chest-animation": {
        "imagen": "assets/ui/opening-chest-animation-id.png", # creo que solo sirve para gold y platinum
        "region": (0.1744, 0.7933, 0.2124, 0.9069),
        "menu_rapido_disponible": False,
        "menu_rapido_tipo": None,
        "botones": {
            "open-1": (0.2703, 0.8252),
            "open-10-or-max": (0.3352, 0.8366),
            "tap": (0.8632, 0.7802), # cancel animation
        },
        "menus": {},
        "subcontexto": {
            "tipo": "currency",
            "valores": {
                "gold-key": {
                    # completar para todas las llaves?
                },
                "karats": { # probablemente siempre alcance solo con este asset, es la condicion de corte
                    "imagen": "assets/ui/open-with-karat.png",
                    "region": (0.319, 0.7925, 0.3488, 0.8342),
                }
            },
        },
    },
}

# ====================
# Interrupciones globales
# ====================

# Imprevistos técnicos o transversales que pueden aparecer en cualquier momento
# sin que el flujo los haya provocado (ej: desconexión, crash, mantenimiento).
# Los gestiona watchdog.py de forma independiente al flujo activo.
#
# Los mensajes de confirmación o advertencia que el flujo sí provoca y espera
# NO van aquí — los maneja el flujo directamente.

INTERRUPCIONES_GLOBALES = {
    # "desconexion": {
    #     "imagen":    "assets/ui/disconnected.png",
    #     "region":    (x1, y1, x2, y2),
    #     "threshold": 0.85,
    #     "botones": {
    #         "reconectar": (x, y),
    #     },
    # },
}

# ====================
# Menú rápido
# ====================

# Estructura unificada del menú rápido: imagen y región para detectar si está abierto,
# y coordenadas de todos sus botones (base, sin offset).
MENU_RAPIDO = { #tome el offset al reves, volver a capturar coords en default, no lobby
    "imagen": "assets/ui/menu-rapido-id.png",
    "region": (0.0501, 0.152, 0.1021, 0.277),
    "botones": {
        "lobby": {"coords": (0.0819, 0.2157), "outcomes": {}, "timeout": 5},
        "mailbox": {"coords": (0.1375, 0.2075), "outcomes": {}, "timeout": 5},
        "awakening": {"coords": (0.2069, 0.2116), "outcomes": {}, "timeout": 5},
        "quests": {"coords": (0.2681, 0.2075), "outcomes": {}, "timeout": 5},
        "inventory": {"coords": (0.0767, 0.357), "outcomes": {}, "timeout": 5},
        "skills": {"coords": (0.1368, 0.357), "outcomes": {}, "timeout": 5},
        "socket": {"coords": (0.2098, 0.3497), "outcomes": {}, "timeout": 5},
        "pets": {"coords": (0.267, 0.3497), "outcomes": {}, "timeout": 5},
        "meteorites": {"coords": (0.0789, 0.5049), "outcomes": {}, "timeout": 5},
        "treasure": {"coords": (0.142, 0.5188), "outcomes": {}, "timeout": 5},
        "companion": {"coords": (0.2013, 0.5074), "outcomes": {}, "timeout": 5},
        "craft": {"coords": (0.2625, 0.4951), "outcomes": {}, "timeout": 5},
        "combine": {"coords": (0.08, 0.643), "outcomes": {}, "timeout": 5},
        "shop": {"coords": (0.1405, 0.6291), "outcomes": {}, "timeout": 5},
        "trading-center": {"coords": (0.2098, 0.6291), "outcomes": {}, "timeout": 5},
        "guild": {"coords": (0.2695, 0.6495), "outcomes": {}, "timeout": 5},
        "character": {"coords": (0.0704, 0.7835), "outcomes": {}, "timeout": 5},
        "char1": {"coords": (0.1405, 0.7892), "outcomes": {}, "timeout": 5},
        "char2": {"coords": (0.1947, 0.7884), "outcomes": {}, "timeout": 5},
        "char3": {"coords": (0.2681, 0.7892), "outcomes": {}, "timeout": 5},
        "close": {"coords": (0.0638, 0.0703), "outcomes": {}, "timeout": 5},
    }
}

# Offset (dx, dy) a aplicar a las coordenadas de MENU_RAPIDO["botones"] según el tipo de contexto.
# "default" no tiene desplazamiento. Otros tipos ajustan solo lo necesario.
MENU_RAPIDO_OFFSET = {
    "default": (0,   0),
    "lobby":   (-80, 0),
}