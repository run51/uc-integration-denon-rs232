# Contexte projet — intégration Denon RS-232 pour Unfolded Circle

Lis ce fichier en début de session. Il contient le contexte et les décisions qui ne sont
pas déductibles du code. Réponds en français.

## Objectif

Piloter un **Denon AVP-A1HD** depuis une **Remote 3** Unfolded Circle, **sans Home Assistant**,
via le port RS-232 de l'ampli et le pont série TCP du **Dock 3**.

Chaîne : `Remote 3 → driver (WebSocket Integration-API) → TCP 5000 → Dock 3 → câble jack/DB9 → Denon`

Remplace un montage ESPHome sur LILYGO T-RSS3 (qui fonctionne et sert de référence/repli).
L'objectif est de supprimer l'ESP **et** la machine Home Assistant de la chaîne.

## État actuel

- Driver complet, 60 tests verts, installé et fonctionnel sur la Remote.
- Validé contre `tests/denon_simulator.py` (faux Denon en TCP) : connexion, interrogation
  d'état, polling 30 s, reconnexion.
- **Validé sur le vrai ampli le 01/11/2026** (v0.1.4, Dock 1 `UCD3-0CCD80` en 192.168.2.143:5000) :
  allumage, source, mode surround, volume, mute et retour d'état dans le widget fonctionnent.
  Dynamic EQ, Dynamic Volume et Reference Level validés en v0.1.5/0.1.6.
  Restent à tester : extinction, zones 2/3/4.
- **Le driver est publié : il expose TOUTES les fonctions de l'ampli** (DSX, zones 2/3/4…),
  même celles que Guillaume n'utilise pas. Ne rien retirer du driver pour son usage perso ;
  adapter plutôt ses activités/pages. (DSX retiré en 0.1.6 puis rétabli en 0.1.7.)
- Guillaume a une **Remote 3 : pas de touches de couleur** (le mapping rouge/vert/jaune → Quick
  ne sert qu'aux Remote Two). Les Quick 1-3 passent par les pages UI.

## Architecture

Deux couches, volontairement indépendantes.

**`intg-denon/denon_control/`** — bibliothèque pure, aucune dépendance Unfolded Circle,
réutilisable depuis Home Assistant ou un CLI :
- `transport.py` : TCP asyncio, framing sur CR, pacing 60 ms, blocage 4 s après `PWON`
- `protocol.py` : parser sans état, une ligne → un `DenonEvent` typé
- `device.py` : modèle d'état + commandes haut niveau, notification par listeners
- `const.py` : **toutes les tables protocole** (sources, modes, paramètres PS)

**`intg-denon/`** — couche UC, bâtie sur `ucapi-framework` (JackJPowell) :
- entités : 1 media player, 1 remote (4 pages UI, 162 commandes simples), 18 selects,
  10 switches, 13 sensors
- `const.py` : définitions **déclaratives** des entités (`SELECTS`, `SWITCHES`, `SENSORS`)
- `device.py` : `PersistentConnectionDevice`, debounce des mises à jour, traduction
  libellé ↔ code protocole

Structure inspirée de `johncarey70/uc-integration-lumagen` (MPL-2.0).

## Pièges du protocole Denon — chacun a son test

Observés sur une capture RS-232 réelle de l'AVP-A1HD. Ne pas les casser :

1. **Trames fragmentées** : `CVFL` puis ` 405\r` en deux lectures. Accumuler jusqu'au CR.
2. **`MVMAX 98`** suit chaque `MV`. Un `startswith("MV")` naïf donnerait −80 dB.
3. **`MSQUICK1`** porte le préfixe `MS` mais n'est pas un mode surround.
4. **`SVDVD` / `SVSOURCE`** sont l'affectation vidéo, pas la source (`SI`).
5. **Séparateurs PS irréguliers** : `PSROOM EQ:AUDYSSEY`, `PSCINEMA EQ.ON`, `PSDSX ONH`.
6. **`PSDYN VOL`** est le paramètre Dynamic EQ (valeur `VOL`) ; `PSDYNSET` est un autre
   paramètre (préfixes testés du plus long au plus court). `PSDYE ON` (ligne tronquée) → `DYN`.
   **L'ampli ignore `PSDYNSET` si `PSDYN` ≠ `VOL`** : `send_raw` envoie `PSDYN VOL` avant.
7. **Requêtes sans réponse** (`PSNIGHT ?`, `PSTONE DEFEAT ?` muets) → architecture 100 % événementielle,
   aucune commande n'attend de réponse.
8. **Après `MVUP`**, l'ampli renvoie l'ancienne puis la nouvelle valeur → debounce 80 ms.
9. **Note K du protocole** : 4 s de silence imposées après `PWON`.
10. **En veille, l'ampli ne répond qu'à `PW?`.**

Décodage des niveaux : `MV30` = −50,0 dB / `MV305` = −49,5 / code 80 = 0 dB.
Canaux `CV` : code 50 = 0 dB, plage 38..62.

## Matériel — vérifié dans le firmware du dock

- **Le Dock 3 intègre un vrai transceiver RS-232.** Pas de MAX3232, pas de convertisseur TTL
  (les notes de version du firmware les déclarent explicitement non supportés).
- **Utiliser le port externe 2 → TCP 5000.** Le port 1 (4999) émet des messages de démarrage
  que l'ampli interpréterait comme des commandes.
- Brochage du cordon : Tip (TX dock) → DB9 broche 3, Ring (RX) → broche 2, Sleeve → broche 5.
- Câble retenu : StarTech `9M351M-RS232-CABLE`. Attention, la plupart des cordons génériques
  utilisent la convention inverse (broche 2 → Tip) et nécessiteraient un null-modem.
- Réglages dock : port 2 en mode RS232 forcé, 9600 8N1, serveur TCP activé. Pas de hot-plug.
- Ces réglages se font dans **l'interface web du Dock** (http://IP-du-dock, mot de passe du Dock),
  pas dans la Remote : avec le firmware 0.10.5, la Remote ne propose pas le mode RS232.
- **Le serveur TCP est une case à part**, « RS232 TCP server (ports 4999, 5000) », décochée par
  défaut. Sans elle, le port 5000 reste fermé même avec le port en RS232.
- Si chaque commande revient à l'identique (écho), c'est que le jack n'est pas enfoncé à fond.

## Points ouverts

1. **L'ampli a reçu le « 3D upgrade »** (nov. 2011) : le protocole de référence est la
   **version 6.0.2** (PDF dans `ref/`, non versionné ; copie sur le NAS `Téléchargements/denon`).
   `PSDYN OFF|ON|VOL` (un seul paramètre), `PSDSX`, `PSREFLEV`, `PSFH:`, `PSPHG` ajoutés ;
   **Night supprimé**. Vérifié en direct le 01/11/2026. L'ancien YAML ESPHome
   (`denonavp.yaml`) est dans le même dossier.
2. **Mute, extinction, zones 2/3/4** : jamais déclenchés dans la capture, modélisés depuis le PDF.
3. **Source list** : les 13 sources non nord-américaines sont présentes. Guillaume élaguera
   ce dont il n'a pas besoin dans `denon_control/const.py::SOURCES` — tout le reste
   (commandes simples, selects, pages UI) se régénère automatiquement.

## Contraintes d'empaquetage (durement acquises)

L'archive installable sur la Remote doit respecter la spécification `core-api`
(`doc/integration-driver/driver-installation.md`) :

- `.tar.gz`, `driver.json` **à la racine**, binaire aarch64 nommé `driver` dans `./bin`
- **Icône : exactement 90×90 px, PNG ou JPG, 16 Ko maximum.** Une icône 256×256 fait rejeter
  l'archive avec « Archive invalide, données manquantes ou métadonnées illisibles ».
- `driver_id` ≥ 5 caractères, minuscules, pas de préfixe `uc_`
- `developer` doit inclure `name`, `email`, `url`

Build : workflow GitHub `Build & Release` (tag `v*` ou déclenchement manuel avec le numéro
de version). Une version ne peut servir qu'une fois — incrémenter à chaque build.
PyInstaller ne cross-compile pas : runner ARM64 obligatoire.

## Environnement de Guillaume

- Windows, dépôt local en `C:\denon`, repo GitHub `run51/uc-integration-denon-rs232`
- Python 3.13 en local (le projet vise 3.11+, le build Remote utilise 3.11)
- **La découverte mDNS entre Windows et la Remote ne fonctionne pas** chez lui — ne pas
  proposer le mode « driver externe sur PC », passer par l'archive installée sur la Remote.
- Tester avec le simulateur : `python tests\denon_simulator.py 5000`, puis configurer
  l'intégration avec l'IP du PC.

## Conventions

- Code et commentaires en anglais, échanges en français.
- Les tables protocole sont la source de vérité : ajouter une source ou un mode se fait
  dans `denon_control/const.py` uniquement.
- Toute correction d'un piège protocole doit s'accompagner d'un test dans
  `tests/test_protocol.py`.
- `pytest` doit rester vert avant tout commit.
