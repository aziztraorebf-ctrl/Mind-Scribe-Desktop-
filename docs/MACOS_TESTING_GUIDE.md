# MindScribe Desktop - Guide de test macOS

## C'est quoi MindScribe ?

MindScribe est une application de dictee vocale pour ton ordinateur. Tu appuies sur un raccourci clavier, tu parles, et le texte est tape automatiquement la ou ton curseur se trouve (navigateur, editeur de code, messagerie, n'importe ou).

L'application a ete developpee et testee sur Windows. On a besoin de toi pour valider qu'elle fonctionne aussi sur macOS.

---

## Ce dont tu as besoin

- Un Mac avec macOS 12+ (Monterey ou plus recent)
- Python 3.11 ou plus recent (verifier avec `python3 --version`)
- Un microphone (celui du Mac fonctionne)
- Une cle API Groq (gratuit) et/ou OpenAI

### Obtenir une cle API Groq (gratuit, 2 minutes)

1. Va sur https://console.groq.com/keys
2. Cree un compte (Google login fonctionne)
3. Clique "Create API Key"
4. Copie la cle (commence par `gsk_...`)

---

## Installation (10 etapes)

Ouvre Terminal (`Cmd+Space`, tape "Terminal", Enter).

### Etape 1 : Verifier Python

```bash
python3 --version
```

Si tu vois `Python 3.11` ou plus, c'est bon. Sinon, installe Python depuis https://www.python.org/downloads/

### Etape 2 : Installer les outils de dev (si pas deja fait)

```bash
xcode-select --install
```

Clique "Install" si une fenetre apparait. Si ca dit "already installed", c'est bon.

### Etape 3 : Cloner le projet depuis GitHub

```bash
cd ~/Desktop
git clone https://github.com/aziztraorebf-ctrl/Mind-Scribe-Desktop-.git
cd Mind-Scribe-Desktop-
```

### Etape 4 : Creer l'environnement Python

```bash
python3 -m venv venv
source venv/bin/activate
```

Tu devrais voir `(venv)` au debut de ta ligne de commande.

### Etape 5 : Installer les dependances

```bash
pip install -r requirements.txt
```

Ca prend 1-2 minutes. Verifie qu'il n'y a pas d'erreur rouge a la fin.

### Etape 6 : Configurer les cles API

```bash
cp .env.example .env
```

Ouvre le fichier `.env` avec un editeur :

```bash
open -e .env
```

Remplace les valeurs :

```
GROQ_API_KEY=gsk_ta_vraie_cle_ici
OPENAI_API_KEY=sk-ta_cle_openai_ici
```

Sauvegarde et ferme. (La cle OpenAI est optionnelle si tu as Groq.)

### Etape 7 : Lancer les tests automatiques

```bash
python -m pytest tests/ -v
```

**Resultat attendu :** `33 passed`. Si des tests echouent, note lesquels.

### Etape 8 : Lancer l'application

```bash
python run.py
```

### Etape 9 : Accorder les permissions macOS

macOS va te demander plusieurs permissions. **Tu dois toutes les accepter :**

1. **Microphone** : Un popup va apparaitre. Clique "OK" / "Allow".
2. **Accessibilite** : Va dans Reglages Systeme > Confidentialite et securite > Accessibilite > ajoute Terminal (ou iTerm)
3. **Surveillance de l'entree** : Reglages Systeme > Confidentialite et securite > Surveillance de l'entree > ajoute Terminal

**Important :** Sans les permissions Accessibilite + Surveillance de l'entree, les raccourcis clavier globaux NE FONCTIONNERONT PAS. Si les hotkeys ne marchent pas, verifie ces permissions en premier.

Apres avoir modifie les permissions, **redemarre l'application** (ferme avec le tray icon > Quit, puis relance `python run.py`).

### Etape 10 : Tester !

Voir la section de tests ci-dessous.

---

## Tests a effectuer

Pour chaque test, note : OK, KO (ne marche pas), ou Partiel (marche mais avec un probleme).

### Test 1 : Demarrage de l'application

- [ ] L'application demarre sans erreur dans le terminal
- [ ] Une icone apparait dans la barre de menu (en haut a droite)
- [ ] Un overlay "MindScribe Ready" apparait au centre de l'ecran
- [ ] L'overlay pulse en vert puis disparait apres ~10 secondes
- [ ] L'overlay fait un fade-in/fade-out (pas un affichage brusque)

**Notes :**

---

### Test 2 : Raccourci clavier (Toggle mode)

- [ ] Appuie sur **Cmd+Shift+Space** (raccourci par defaut sur Mac)
- [ ] L'overlay "Recording" apparait avec une barre d'animation
- [ ] Un timer s'affiche (00:00, 00:01, ...)
- [ ] Parle pendant quelques secondes
- [ ] Appuie a nouveau sur **Cmd+Shift+Space**
- [ ] L'overlay passe a "Transcribing..."
- [ ] Apres quelques secondes, le texte est colle dans le champ actif
- [ ] Une notification "Transcription complete" apparait

**Astuce :** Ouvre TextEdit ou Notes avant de tester, pour avoir un champ de texte actif.

**Notes :**

---

### Test 3 : Barre de menu (tray icon)

- [ ] L'icone dans la barre de menu change d'apparence selon l'etat (idle / recording / transcribing)
- [ ] Clic droit (ou Ctrl+clic) sur l'icone affiche un menu
- [ ] Le menu affiche "Toggle Recording (Cmd+Shift+Space)" (ou le hotkey actuel)
- [ ] "Settings" ouvre une fenetre de parametres
- [ ] "Quit" ferme l'application proprement

**Notes :**

---

### Test 4 : Fenetre de parametres (Settings)

- [ ] La fenetre s'ouvre avec un theme sombre
- [ ] Les menus deroulants fonctionnent (Language, Provider, Model, Microphone, Hotkey)
- [ ] Le dropdown Hotkey affiche 7 options avec "Cmd" (pas "Ctrl")
- [ ] Le bouton "Test" pour le hotkey fonctionne :
  - [ ] Clique "Test"
  - [ ] Le label dit "Press Cmd + Shift + Space now..."
  - [ ] Appuie sur le raccourci
  - [ ] Le label passe en vert "OK - detected!"
- [ ] Le bouton "Save" sauvegarde et ferme la fenetre
- [ ] Le bouton "Cancel" ferme sans sauvegarder

**Notes :**

---

### Test 5 : Enregistrement avec F9

- [ ] Ouvre Settings, change le hotkey pour "F9"
- [ ] Clique "Test", appuie sur F9, verifie "OK - F9 detected!"
- [ ] Clique "Save"
- [ ] Appuie sur F9 -> l'enregistrement demarre
- [ ] Appuie sur F9 -> l'enregistrement s'arrete et transcrit
- [ ] Le texte est colle correctement

**Notes :**

---

### Test 6 : Mode Hold

- [ ] Ouvre Settings, change Record Mode en "Hold to Record"
- [ ] Clique Save
- [ ] Maintiens Cmd+Shift+Space (ou F9) enfonce pendant 3+ secondes
- [ ] L'enregistrement demarre quand tu appuies
- [ ] L'enregistrement s'arrete quand tu relaches
- [ ] La transcription se fait automatiquement

**Notes :**

---

### Test 7 : Overlay - Apparence et comportement

- [ ] L'overlay est semi-transparent (on voit a travers)
- [ ] L'overlay reste au-dessus des autres fenetres
- [ ] L'overlay est draggable (clique et tire pour deplacer)
- [ ] Les boutons Pause, Stop, Cancel sont visibles et cliquables
- [ ] La police est lisible et propre (pas de texte coupe ou bizarre)

**Notes :**

---

### Test 8 : Notifications

- [ ] Une notification macOS native apparait apres transcription
- [ ] Une notification apparait si l'enregistrement est trop court
- [ ] Les notifications sont dans le Centre de notifications macOS

**Notes :**

---

### Test 9 : Pause / Cancel

- [ ] Pendant un enregistrement, clique "Pause" sur l'overlay
- [ ] Le timer se fige, le texte passe a "Paused"
- [ ] Clique "Resume" -> l'enregistrement reprend
- [ ] Pendant un enregistrement, clique "Cancel"
- [ ] L'enregistrement est annule (pas de transcription)

**Notes :**

---

### Test 10 : Cas limites

- [ ] Enregistrement tres court (< 0.5 sec) -> message "too short"
- [ ] Pas de microphone branche -> message d'erreur clair
- [ ] Pas de cle API -> message d'erreur clair
- [ ] Deux appuis rapides sur le hotkey -> pas de crash

**Notes :**

---

## Problemes connus a verifier

Ces points sont specifiques a macOS et n'ont pas encore ete testes :

1. **Permissions** : Est-ce que les popups de permission apparaissent correctement ?
2. **Hotkeys globaux** : Est-ce que Cmd+Shift+Space fonctionne partout (meme quand une autre app est au premier plan) ?
3. **Overlay transparency** : Est-ce que `-alpha` fonctionne sur macOS ou est-ce que l'overlay est opaque ?
4. **tkinter sur macOS** : Est-ce que les boutons, scrollbars, et dropdowns s'affichent correctement ?
5. **Tray icon sur macOS** : Est-ce que l'icone apparait dans la barre de menu ? (pystray sur macOS utilise `rumps` ou AppKit en backend)
6. **Font SF Pro Display** : Est-ce que le texte s'affiche avec la bonne police ou est-ce qu'il y a un fallback visible ?
7. **Notifications** : Est-ce que `osascript` affiche les notifications correctement ?

---

## Format du feedback

Pour chaque test, donne-moi :

```
Test X : [OK / KO / Partiel]
  Description du probleme (si KO ou Partiel) :
  Screenshot (si possible) :
  Message d'erreur dans le terminal (si visible) :
```

Et note aussi :

- **Version macOS** : (ex: Sonoma 14.2)
- **Version Python** : (copie le resultat de `python3 --version`)
- **Type de Mac** : (Intel ou Apple Silicon M1/M2/M3)
- **Resultat des tests automatiques** : (33 passed ?)

---

## En cas de probleme

### L'application ne demarre pas
Copie les 20 dernieres lignes du terminal et envoie-les moi.

### Les hotkeys ne marchent pas
1. Verifie Reglages Systeme > Confidentialite > Accessibilite
2. Verifie Reglages Systeme > Confidentialite > Surveillance de l'entree
3. Redemarre Terminal
4. Relance `python run.py`

### Erreur "No module named ..."
```bash
source venv/bin/activate
pip install -r requirements.txt
```

### Erreur API (401, 403, etc.)
Verifie que ton `.env` contient la bonne cle API.

---

Merci pour ton aide !
