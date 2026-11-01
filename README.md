# Denon AVP-A1HD RS-232 — Unfolded Circle integration

Pilote un Denon AVP-A1HD (et tout Denon/Marantz parlant le protocole ASCII classique
`PWON` / `MV80` / `SIDVD`) depuis une Remote Two/3, **sans Home Assistant**, en passant
par le port RS-232 de l'ampli et une passerelle série-vers-IP — typiquement le serveur TCP
du **Dock 3 Unfolded Circle** (ports 4999/5000), mais aussi Global Caché IP2SL/iTach,
USR-TCP232, ser2net…

```
Remote 3 ──WS──▶ ce driver ──TCP 5000──▶ Dock 3 ──câble jack 3,5 mm / DB9──▶ Denon
```

Retour d'état temps réel : l'ampli pousse spontanément chaque changement, le driver met à
jour les entités sans polling agressif (un rafraîchissement toutes les 30 s en filet).

## Entités

| Type | Contenu |
|---|---|
| **Media player** | Power, volume (0-100 ↔ −80…+18 dB), mute, liste de sources, liste de modes surround, D-pad, menu |
| **Remote** | Touches physiques mappées, 4 pages UI (Sources, Surround, Audyssey, Quick/Zones), 155 commandes simples, pass-through brut |
| **17 Selects** | Source, Surround, Input mode, Digital mode, Quick Select, Room EQ, Dynamic EQ (Off / EQ / EQ + Volume), Dynamic Volume (Day / Evening / Midnight), Reference Level, PLIIz Height Gain, Audio Restorer, PL mode, DRC, D.COMP, sources zones 2/3/4 |
| **10 Switches** | Mute, Main zone, PLIIz Height, Cinema EQ, Tone Defeat, zones 2/3/4, mute zones 2/3 |
| **12 Sensors** | Volume (dB), source, surround, input mode, quick select, Room EQ, Dyn EQ, Dyn Vol, Restorer, zone 2 |

## Matériel

### Le Dock 3 intègre un vrai transceiver RS-232

**Aucun convertisseur de niveaux n'est nécessaire.** Le dock produit du RS-232 normalisé
directement sur le jack : un simple cordon jack 3,5 mm ↔ DB9 suffit.

À l'inverse, les adaptateurs UART TTL ne sont pas supportés, leurs niveaux de signal étant
différents — ne branchez pas un module MAX3232 ou un convertisseur TTL entre les deux.

### Utilisez le port externe 2 (TCP 5000)

Sur les docks actuels, le mode RS232 est limité au port externe 2. Le port 1 peut émettre au
démarrage des messages système que l'ampli interpréterait comme des commandes — la console de
boot de l'ESP32 partirait dans le Denon.

| Port externe du dock | Port TCP | Utilisable en RS232 |
|---|---|---|
| 1 | 4999 | non recommandé |
| **2** | **5000** | **oui** |

### Brochage du cordon

Côté dock, en mode RS232 : **Tip = TX**, **Ring = RX**, **Sleeve = GND**. Unfolded Circle
insiste sur le respect strict de ce brochage pour les câbles faits maison, sous peine de
problèmes de détection ou de dommages.

Le Denon est un DCE avec DB9 femelle : broche 2 = TxD (il émet), broche 3 = RxD (il reçoit),
broche 5 = GND. Le câble est donc croisé :

| Jack 3,5 mm (dock) | DB9 mâle (vers Denon) |
|---|---|
| **Tip** — TX du dock | **broche 3** — RxD du Denon |
| **Ring** — RX du dock | **broche 2** — TxD du Denon |
| **Sleeve** — GND | **broche 5** — GND |

**Câble du commerce compatible** : StarTech `9M351M-RS232-CABLE` (DB9 mâle ↔ jack 3,5 mm, 1 m,
~15-20 €), dont le brochage est broche 3 → Tip, broche 2 → Ring, broche 5 → Sleeve.

Méfiance sur les cordons génériques : certains adoptent la convention inverse (Tip = TxD du
DB9). Vérifiez la fiche technique ou testez la continuité au multimètre. En cas d'erreur, rien
ne casse — ça ne communique simplement pas, il suffit d'inverser Tip et Ring.

Pas de hot-plug : branchez avant de mettre le dock sous tension, sous peine de brownout.

### Configuration du Dock 3

Firmware ≥ 0.10.3. Dans les options du dock (UI web embarquée ou API WebSocket) :

1. **Port externe 2** en mode **RS232** (le mode doit être forcé, pas laissé en Auto).
2. **9600 bauds, 8N1.**
3. **Serveur TCP RS232 activé** (option « Serveur TCP RS232 (ports 4999, 5000) »).
4. Terminateur : `13` (CR) ou mode chunk immédiat — le driver réassemble les trames
   lui-même, les deux fonctionnent.

Test rapide sans le driver, depuis un terminal sur votre PC :

```
nc <ip-du-dock> 5000
PW?          ← taper puis Entrée
PWSTANDBY    ← réponse du Denon (ou PWON)
```

Si rien ne revient : inverser Tip/Ring, vérifier que le port 2 est bien en mode RS232 à
9600 bauds, et que le serveur TCP est activé.

## Lancer le driver

### Docker (recommandé pour tester)

```bash
git clone <ce-repo> && cd uc-integration-denon-rs232
mkdir -p config
docker compose up -d --build
docker compose logs -f
```

`network_mode: host` est nécessaire pour que la Remote découvre le driver en mDNS. Si votre
hôte Docker ne le permet pas (Synology, Windows), mettez `UC_DISABLE_MDNS_PUBLISH=true`,
exposez le port 9092 et ajoutez l'intégration manuellement sur la Remote avec
`http://<ip-du-docker>:9092`.

Le dossier `./config` conserve la configuration (`config.json`) entre redémarrages.

### Sur la Remote (custom integration)

```bash
./build-dev.sh      # produit uc-intg-denon_rs232-<version>-aarch64.tar.gz
```

Puis web-configurator → Intégrations → Ajouter → Installer une intégration personnalisée →
uploader l'archive. Ou via l'[Integration Manager](https://github.com/JackJPowell/uc-intg-manager).
Un tag `v*` sur GitHub déclenche le workflow qui construit et publie l'archive.

### En local (développement)

```bash
pip install -r requirements-dev.txt
cd intg-denon && UC_CONFIG_HOME=../config python driver.py
```

## Configuration dans la Remote

Intégrations → Ajouter → *Denon AVP-A1HD (RS-232)* → renseigner :

- Nom
- IP de la passerelle (celle du **dock**, pas du Denon)
- Port TCP : `5000` (port externe 2 du dock — voir plus haut)
- Vérification `PW?` : cochée, le setup refuse d'enregistrer si le Denon ne répond pas en 4 s.
  Décocher pour enregistrer quand même (câblage à finir plus tard).

## Personnaliser

Tout est déclaratif dans deux fichiers :

- **Sources / modes / paramètres** : `intg-denon/denon_control/const.py`
  (`SOURCES`, `SURROUND_MODES`, `ROOM_EQ_MODES`…). Retirer une entrée de `SOURCES` la retire
  de la liste du media player, du select, de la page UI et des commandes simples.
- **Entités** : `intg-denon/const.py` (`SELECTS`, `SWITCHES`, `SENSORS`). Une ligne par entité.

### Commandes simples et pass-through

L'entité Remote expose des noms comme `SOURCE_DVD`, `SURROUND_7CH_STEREO`, `ROOM_EQ_AUDYSSEY`,
`DYN_VOL_EVE`, `QUICK1`, `ZONE2_ON`. Dans « Envoyer une commande » d'une activité, tout ce
qui commence par un préfixe Denon connu (`PS`, `CV`, `MS`, `Z2`…) est envoyé **tel quel** :

```
PSSB:MTRX ON
CVFL 505
raw:MNMEN ON
```

## Tests

```bash
pytest                                   # 59 tests : parser (rejoue une capture réelle), transport, bout-en-bout
python tests/denon_simulator.py 5000     # faux Denon sur TCP pour tester la Remote sans matériel
```

Le simulateur reproduit les comportements observés sur l'appareil réel : `MVMAX 98` après
chaque `MV`, `MSQUICK1`, rafale d'état après `PWON`, trames fragmentées, silence en standby.

## Détails du protocole gérés

Observés sur une capture RS-232 réelle et couverts par des tests :

- Réponses coupées entre deux lectures (`CVFL` … ` 405\r`) — réassemblage sur CR.
- `MVMAX 98` suit chaque `MV` : c'est le maximum, pas le volume.
- `MSQUICK1` porte le préfixe `MS` mais n'est pas un mode surround.
- `SVDVD` / `SVSOURCE` sont l'affectation vidéo, pas la source.
- Séparateurs PS irréguliers : `PSROOM EQ:AUDYSSEY`, `PSCINEMA EQ.ON`, `PSDSX ONH`.
- `PSDYN VOL` est le paramètre Dynamic EQ (valeur `VOL`), à ne pas confondre avec `PSDYNSET`.
- Après `MVUP`, l'ampli renvoie l'ancienne puis la nouvelle valeur — mises à jour dé-rebondies.
- Certaines requêtes restent sans réponse (`PSNIGHT ?`, `PSTONE DEFEAT ?`) — architecture 100 % événementielle,
  aucune commande n'attend de réponse.
- 4 s de silence imposées après `PWON` (note K du protocole), puis rafraîchissement complet.

### Protocole « 3D upgrade »

Le driver suit le protocole Denon **6.0.2** de l'AVP-A1HD mis à jour (« 3D upgrade » de
novembre 2011), vérifié sur l'appareil réel le 01/11/2026 :

- Dynamic EQ / Dynamic Volume = **un seul paramètre** `PSDYN OFF|ON|VOL`
  (`ON` = Dynamic EQ seul, `VOL` = Dynamic EQ + Dynamic Volume), réglage `PSDYNSET DAY|EVE|NGT`.
- Ajouts : Audyssey DSX `PSDSX OFF|ONH|ONW`, largeur/hauteur de scène `PSSTW` / `PSSTH`,
  niveau de référence `PSREFLEV 0|5|10|15`, Dolby PLIIz `PSFH:ON|OFF` et `PSPHG LOW|MID|HI`.
- **Night mode supprimé** par la mise à jour : `PSNIGHT` n'existe plus.

## Crédits

Structure inspirée de [uc-integration-lumagen](https://github.com/johncarey70/uc-integration-lumagen)
(John Carey, MPL-2.0) et construite sur [ucapi-framework](https://github.com/JackJPowell/ucapi-framework)
(Jack Powell). Pont série du Dock 3 : [ucd3-firmware PR #72](https://github.com/unfoldedcircle/ucd3-firmware/pull/72).

Licence : MPL-2.0.
