# bot/constants.py

import os
from dotenv import load_dotenv

# Carga las variables del archivo .env
load_dotenv()

# Si no encuentra la variable en el .env, usa el valor por defecto
DISPOSITIVO_ADB = os.getenv("DISPOSITIVO_ADB", "SERIAL_POR_DEFECTO") # serial USB, no IP
SCRCPY_SERVER_PATH = os.getenv("SCRCPY_SERVER_PATH", r"ruta\generica\scrcpy-server")
ADB_PATH           = "adb"                  # o ruta completa si no está en PATH

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
            "season-pass": (0.0678, 0.2018),
            "time-rewards": (0.0619, 0.3162),
            "menu-rapido": (0.0789, 0.0654),
            "shop": (0.0793, 0.8815),
            "black-market": (0.1667, 0.893),
            "trading-center": (0.2441, 0.893),
            "buffs": (0.5852, 0.9101),
            "quests": (0.653, 0.9126),
            "treasure": (0.722, 0.9167),
            "enhance": (0.795, 0.9297),
            "craft": (0.8536, 0.9093),
            "combine": (0.9237, 0.9191),
            "meteorites": (0.9296, 0.7753),
            "pets": (0.8599, 0.7745),
            "socket": (0.795, 0.777),
            "skills": (0.7209, 0.7704),
            "inventory": (0.6479, 0.7884),
            "awakening": (0.58, 0.7884),
            "battle": (0.8529, 0.598),
            "survival": (0.8097, 0.4297),
            "stage": (0.8138, 0.2876),
            "companion": (0.6504, 0.6095),
            "guild": (0.7891, 0.0858),
            "friends": (0.8374, 0.0784),
            "mailbox": (0.8886, 0.0694),
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
            "select": (0.6855, 0.9101),
            "last-character-after-scroll": (0.7754, 0.5964)
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
            "menu-rapido": (0.198, 0.0694),
            "back": (0.8009, 0.067),
            "elite": (0.8035, 0.1789),
            "menu-world-map": (0.7305, 0.1895),
            "dispatch": (0.6726, 0.1928),
            "x4-stamina": (0.8105, 0.9216),
            "x3-stamina": (0.7629, 0.9142),
            "x2-stamina": (0.7176, 0.9126),
            "x1-stamina": (0.6718, 0.9118),
            "daily-dungeon": (0.5697, 0.9003),
            "claim": (0.427, 0.933),
            "prev-ep": (0.0409, 0.54),
            "next-ep": (0.9838, 0.54)
        },
        "menus": {
            "world-map": {
                "imagen":  "assets/ui/world-map-menu-id.png",
                "region":  (98, 64, 139, 103),
                "botones": {
                    "ep-01": (119, 84),
                    "ep-02": (191, 83),
                    "ep-03": (246, 81),
                    "ep-04": (317, 85),
                    "ep-05": (381, 84),
                    "ep-06": (450, 85),
                    "ep-07": (512, 84),
                    "ep-08": (579, 84),
                    "ep-09": (647, 84),
                    "ep-10": (714, 85),
                    "ep-11": (121, 141),
                    "ep-12": (187, 140),
                    "ep-13": (250, 145),
                    "ep-14": (315, 141),
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
                        "stage-01": (0.2294, 0.3668),
                        "stage-02": (0.3411, 0.4346),
                        "stage-03": (0.444, 0.3685),
                        "stage-04": (0.5542, 0.4404),
                        "stage-05": (0.6541, 0.3709),
                        "stage-06": (0.7625, 0.4632),
                        "stage-07": (0.7592, 0.7386),
                        "stage-08": (0.6622, 0.6528),
                        "stage-09": (0.556, 0.75)
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
            "x1": (0.4369, 0.1062),
            "x2": (0.4882, 0.1087),
            "x3": (0.5365, 0.1062),
            "x4": (0.5878, 0.1111),
            "buff-1": (0.5391, 0.5384),
            "buff-2": (0.6125, 0.5343),
            "buff-3": (0.6869, 0.5221),
            "buff-4": (0.7585, 0.5261),
            "difficulty-1": (0.2345, 0.9126),
            "difficulty-2": (0.3079, 0.9093),
            "difficulty-3": (0.3827, 0.8995),
            "difficulty-4": (0.4513, 0.8938),
            "get-support": (0.7459, 0.7917),
            "start": (0.7364, 0.9118),
            "close": (0.8042, 0.174),
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
            "start": (0.5737, 0.8913),
            "auto": (0.4192, 0.8905),
            "close": (0.6622, 0.098),
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
            "max": (0.3348, 0.7982),
            "video": (0.3569, 0.8971),
            "auro-repeat": (0.5527, 0.9052),
            "auto-continue": (0.7279, 0.902),
            "close": (0.8326, 0.0474),
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
            "fill-all": (0.5988, 0.8472),
            "close": (0.7397, 0.0842),
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
            "ok": (0.4974, 0.8611)
        },
        "menus":       {},
        "subcontexto": None
    },
    "survival": {
        "imagen": "assets/ui/survival-id.png",
        "region": (0.1707, 0.2337, 0.2994, 0.2974),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": (0.1906, 0.0711),
            "back": (0.8053, 0.0866),
            "monster-wave": (0.2389, 0.3995),
            "companion-battle": (0.4115, 0.4118),
            "world-boss": (0.3514, 0.7843),
            "tot": (0.5708, 0.4542),
            "tower-of-proof": (0.7423, 0.4142),
            "labyrinth": (0.5763, 0.8039),
            "expedition": (0.7345, 0.7958)
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
            "menu-rapido": (0.1785, 0.0523),
            "back": (0.8079, 0.0547),
            "penance-after-scroll": (0.2625, 0.8791),
            "buff-1": (0.5572, 0.3186),
            "buff-2": (0.6268, 0.3113),
            "buff-3": (0.7117, 0.3301),
            "buff-4": (0.7806, 0.3121),
            "skip": (0.7636, 0.7092),
            "start": (0.7651, 0.8734),
            "max-sapphires": (0.7898, 0.6021),
            "x3-sapphires": (0.7423, 0.6046),
            "x2-sapphires": (0.6903, 0.5907),
            "x1-sapphires": (0.6405, 0.6005),
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
            "ok": (0.5018, 0.8121),
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
            "yes": (0.4381, 0.6324),
            "no": (0.58, 0.6209),
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
            "ok": (0.5015, 0.6585)
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
            "ok": (0.4959, 0.759),
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
            "buy-item-01": (0.4491, 0.3415),
            "buy-item-02": (0.4506, 0.4698),
            "buy-item-03": (0.4524, 0.5948),
            "buy-item-04": (0.4539, 0.7337),
            "buy-item-05": (0.4454, 0.8725),
            "buy-item-06": (0.7592, 0.3415),
            "buy-item-07": (0.757, 0.4706),
            "buy-item-08": (0.7507, 0.6095),
            "buy-item-09": (0.7592, 0.7377),
            "buy-item-10": (0.7592, 0.8717),
            "refresh": (0.5723, 0.2157),
            "close": (0.8097, 0.1324),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "sold-by",
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
            "yes": (0.4347, 0.634),
            "no": (0.569, 0.6307),
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
            "race": (0.2201, 0.2018),
            "growth": (0.3127, 0.2222),
            "menu-rapido": (0.2024, 0.0621),
            "back": (0.8009, 0.0842),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "tab",
            "valores": {
                "race": {
                    "imagen": "assets/ui/season-pass-race-id.png",
                    "region": (0.3156, 0.4918, 0.3835, 0.576),
                    "botones":   {
                        "claim-all": (0.3451, 0.6536),
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
            "yes": (0.4336, 0.6242),
            "no": (0.569, 0.6258),
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
            "close": (0.8208, 0.1021),
            "reward-01": (0.285, 0.4755),
            "reward-02": (0.5044, 0.4706),
            "reward-03": (0.7058, 0.4706),
            "reward-04": (0.2902, 0.7745),
            "reward-05": (0.5026, 0.7639),
            "reward-06": (0.715, 0.7614),
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
            "arena": (0.2847, 0.424),
            "league-match": (0.4908, 0.3685),
            "invasion": (0.2872, 0.7426),
            "ranker-break": (0.4779, 0.7288),
            "melee": (0.7286, 0.7165),
            "back": (0.8013, 0.0743),
            "menu-rapido": (0.205, 0.0564),
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
            "menu-rapido": (0.1914, 0.0678),
            "back": (0.8001, 0.0858),
            "beginner": (0.2806, 0.6479),
            "intermediate": (0.483, 0.5727),
            "expert": (0.7459, 0.585),
            "refresh": (0.7688, 0.9461),
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
            "x2": (0.6615, 0.7312),
            "x3": (0.7076, 0.7312),
            "x5": (0.743, 0.7361),
            "x8": (0.7902, 0.7304),
            "buff-1": (0.5509, 0.3758),
            "buff-2": (0.6763, 0.3619),
            "buff-3": (0.7681, 0.3603),
            "menu-rapido": (0.194, 0.0703),
            "back": (0.7968, 0.0645),
            "start": (0.7677, 0.9534),
            "auto-repeat": (0.7603, 0.8521),
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
            "close": (0.6847, 0.1021),
            "auto-repeat": (0.5052, 0.8799),
            "upon-defeat": (0.6608, 0.7721),
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
            "tap": (0.4875, 0.8889),
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
            "ok": (0.4934, 0.6291),
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
            "pause": (0.8182, 0.183),
            "auto-repeat": (0.5018, 0.7525),
        },
        "menus":       {},
        "subcontexto": {
            "tipo": "toggle",
            "valores": {
                "auto-repeat-off": {
                    "imagen": "assets/ui/arena-auto-repeat-toggle-off.png",
                    "region": (0.4336, 0.7173, 0.5656, 0.777),
                },
                "auto-repeat-on": {
                    "imagen": "assets/ui/arena-auto-repeat-toggle-on.png",
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
            "ok": (0.4941, 0.7288),
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
            "ok": (0.4993, 0.6683),
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
            "close": (0.8197, 0.1675),
            "account-mail": (0.2618, 0.2786),
            "character-mail": (0.382, 0.2778),
            #"striker-rewards": (0.5077, 0.2884), # no real use cases
            "friends": (0.6235, 0.2827),
            "claim-all": (0.4764, 0.3546),
            "delete-read": (0.2898, 0.357),
            "claim-pos1": (0.7493, 0.4575),
            "claim-pos2": (0.7485, 0.576),
            "claim-pos3": (0.7474, 0.7002),
            "claim-pos4": (0.7485, 0.8121),
            "claim-bottom-after-scroll": (0.7482, 0.8636),
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
            "close": (0.8127, 0.107),
            "send-res-to-all": (0.7662, 0.8889),
            "delete": (0.5597, 0.8954),
            "list": (0.2364, 0.2083),
            "recommended": (0.3418, 0.2181),
            "pending": (0.4458, 0.2165),
            "page-down": (0.3879, 0.924),
            "page-up": (0.2935, 0.9232),
            "slot-1": (0.4473, 0.3636),
            "slot-2": (0.4458, 0.5082),
            "slot-3": (0.4458, 0.6454),
            "slot-4": (0.448, 0.8031),
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
            "yes": (0.4347, 0.6364),
            "no": (0.5737, 0.6283),
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
            "ok": (0.5015, 0.6283),
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
            "ok": (0.4967, 0.6422),
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
            "close": (0.8256, 0.0948),
            "claim-all": (0.6973, 0.1364),
            "claim-karat": (0.6921, 0.3292),
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
            "yes": (0.4395, 0.6332),
            "no": (0.5697, 0.6291),
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
            "back":           (851, 32),
            "menu-rapido":    (134, 41),
            "physical-tower": (189, 130),
            "magical-tower":  (366, 134),
            "socket":         (810, 313),
            "start":          (806, 522),
            "auto-repeat":    (808, 480),
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
            "auto-repeat": (562, 399),
            "auto-continue": (743, 388),
            "close": (854, 83),
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
            "ok": (486, 335)
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
            "ok": (477, 338),
        },
        "menus":       {},
        "subcontexto": None
    },
    "socket": {
        "imagen": "assets/ui/socket-id.png",
        "region": (0.5409, 0.2361, 0.6095, 0.3154),
        "threshold": 0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido": (0.1999, 0.0743),
            "back": (0.8009, 0.0768),
            "socket": (0.1987, 0.1904),
            "equipment-home": (0.3131, 0.1838),
            "enhance-gem-absorption": (0.4277, 0.1855),
            "enhance-all": (0.6206, 0.9534),
            "next-page": (0.7987, 0.9461),
            "prev-page": (0.7043, 0.942),
            "bag-slot-01": (0.5808, 0.402),
            "bag-slot-02": (0.6504, 0.4109),
            "bag-slot-03": (0.7124, 0.406),
            "bag-slot-04": (0.7858, 0.3995),
            "bag-slot-05": (0.5848, 0.5408),
            "bag-slot-06": (0.6486, 0.5498),
            "bag-slot-07": (0.7187, 0.54),
            "bag-slot-08": (0.7876, 0.5425),
            "bag-slot-09": (0.5826, 0.6781),
            "bag-slot-10": (0.6512, 0.6748),
            "bag-slot-11": (0.7201, 0.6895),
            "bag-slot-12": (0.7788, 0.6944),
            "bag-slot-13": (0.5808, 0.817),
            "bag-slot-14": (0.6538, 0.8186),
            "bag-slot-15": (0.7153, 0.8219),
            "bag-slot-16": (0.7847, 0.8211),
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
            "close": (0.7482, 0.1601),
            "gold-enhance": (0.3875, 0.8382),
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
            "ok": (0.4934, 0.634),
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
            "sell-bulk": (0.4004, 0.6332),
            "sell": (0.4967, 0.6258),
            "cancel": (0.5985, 0.6364),
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
            "close": (0.7813, 0.1511),
            "general": (0.2924, 0.2418),
            #"pets": (0.3861, 0.2484),           # no real use cases
            "avatar-and-keys": (0.4753, 0.25),
            "currency": (0.5815, 0.2418),
            #"special-currency": (0.6881, 0.25), # no real use cases
            "events": (0.1873, 0.2786),
            #"premium-coins": (0.1869, 0.3856),  # no real use cases
            "trade-slot-1": (0.7091, 0.4297),
            "trade-slot-2": (0.7076, 0.5727),
            "trade-slot-3": (0.7065, 0.7214),
            "trade-slot-4": (0.7098, 0.8824),
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
            "ok": (0.5026, 0.6307),
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
            "no": (0.3599, 0.7778),
            "trade": (0.5026, 0.7778),
            "max-available-trades": (0.7043, 0.8137),
            "plus-one-available-trade": (0.6685, 0.8056),
            "minus-one-available-trade": (0.5848, 0.8007),
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
            "ok": (0.5044, 0.6258),
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
            "ok": (0.5007, 0.6299),
        },
        "menus":       {},
        "subcontexto": None
    },
    "craft": {
        "imagen":                 "assets/ui/craft-id.png",
        "region":                 (387, 263, 484, 289),
        "threshold":              0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido":            (104, 33),
            "back":                   (837, 45),
            "weapon-hero-craft":      (872, 192),
            "armor-hero-craft":       (871, 339),
            "accessories-hero-craft": (873, 475),
        },
        "menus":       {},
        "subcontexto": None,
    },
    "meteorites": {
        "imagen":                 "assets/ui/meteorites-id.png",
        "region":                 (87, 81, 187, 116),
        "threshold":              0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido":  (106, 36),
            "back":         (846, 49),
            "meteorites":   (140, 100),
            "combine":      (252, 100),
            "evolve":       (343, 92),
            "reforge":      (437, 107),
            "reroll":       (551, 100),
            "set-1":        (138, 155),
            "set-2":        (206, 152),
            "set-3":        (265, 155),
            "equipped-all": (627, 138),
            "bag-slot-00":  (576, 214),
            "bag-slot-01":  (663, 207),
            "bag-slot-02":  (748, 213),
            "bag-slot-03":  (820, 206),
            "bag-slot-10":  (572, 280),
            "bag-slot-11":  (662, 279),
            "bag-slot-12":  (738, 280),
            "bag-slot-13":  (828, 284),
            "bag-slot-20":  (585, 362),
            "bag-slot-21":  (660, 352),
            "bag-slot-22":  (748, 353),
            "bag-slot-23":  (822, 361),
            "bag-slot-30":  (574, 430),
            "bag-slot-31":  (666, 426),
            "bag-slot-32":  (740, 428),
            "bag-slot-33":  (819, 434),
        },
        "menus": {
            "current-meteorite": {
                "imagen":  "assets/ui/current-meteorite-id.png",
                "region":  (116, 217, 181, 286),
                "botones": {
                    "equip-unequip":  (141, 173),
                    "enhance":        (144, 245),
                    "reforge-evolve": (141, 327),
                    "reroll-reforge": (142, 401),
                }
            }
        },
        "subcontexto": {
            "tipo": "meteorite-set",
            "valores": {
                "set-1": {
                    "imagen":  "assets/ui/set-1-id.png",
                    "region":  (102, 129, 169, 170),
                    "botones": {},
                },
                "set-2": {
                    "imagen":  "assets/ui/set-2-id.png",
                    "region":  (165, 129, 234, 172),
                    "botones": {},
                },
                "set-3": {
                    "imagen":  "assets/ui/set-3-id.png",
                    "region":  (229, 128, 299, 171),
                    "botones": {},
                },
            }
        },
    },
    "treasure": {
        "imagen":                 "assets/ui/treasure-id.png",
        "region":                 (365, 150, 480, 302),
        "threshold":              0.85,
        "menu_rapido_disponible": True,
        "menu_rapido_tipo":       "default",
        "botones": {
            "menu-rapido":    (109, 42),
            "back":           (836, 45),
            "bronze-chest":   (422, 242),
            "silver-chest":   (559, 236),
            "gold-chest":     (680, 234),
            "platinum-chest": (805, 260),
        },
        "menus": {
            "gold-chest-menu": {
                "imagen":  "assets/ui/gold-chest-menu-id.png",
                "region":  (670, 222, 762, 313),
                "botones": {
                    "open-1":  (634, 260),
                    "open-10": (714, 264),
                }
            }
        },
        "subcontexto": None,
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
MENU_RAPIDO = {
    "imagen":  "assets/ui/menu-rapido-id.png",
    "region":  (16, 77, 84, 152),
    "botones": {
        "lobby":            (125, 121),
        "mailbox":          (204, 110),
        "awakening":        (288, 116),
        "quests":           (366, 123),
        "inventory":        (132, 178),
        "skills":           (208, 193),
        "socket":           (278, 184),
        "pets":             (360, 178),
        "meteorites":       (121, 268),
        "treasure":         (208, 267),
        "companion":        (289, 267),
        "craft":            (358, 267),
        "combine":          (126, 351),
        "shop":             (204, 347),
        "trading-center":   (286, 349),
        "guild":            (351, 346),
        "select-character": (121, 427),
        "character-1":      (208, 426),
        "character-2":      (276, 424),
        "character-3":      (362, 428),
    }
}

# Offset (dx, dy) a aplicar a las coordenadas de MENU_RAPIDO["botones"] según el tipo de contexto.
# "default" no tiene desplazamiento. Otros tipos ajustan solo lo necesario.
MENU_RAPIDO_OFFSET = {
    "default": (0,   0),
    "lobby":   (-80, 0),
}