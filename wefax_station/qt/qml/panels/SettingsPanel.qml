import QtQuick
import QtQuick.Layouts
import "../components" as C
import ".." as T

/*
 * SettingsPanel.qml — Onglet PARAMÈTRES
 *
 * Recrée la fenêtre Settings Tkinter (SettingsTabsMixin) :
 *   - Connexion radio (repris depuis RadioPanel pour cohérence)
 *   - Profil opérateur
 *   - Préférences d'interface (y compris choix UI Tkinter/Qt)
 *   - Archives & stockage
 *   - Diagnostic
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property int    activeSection:  0

    // Profil opérateur
    property string callsign:   ""
    property string qth:        ""
    property string locator:    ""
    property string continent:  "EU"
    property string assoc:      ""   // Ex : ADRASEC

    // Interface
    property string uiMode:     "qt"   // "qt" ou "tk"
    property string theme:      "dark"
    property bool   compactMode: false
    property bool   startAudioAuto: true
    property string workspaceDir: ""

    // Archives
    property string archiveDir:  ""
    property int    keepDays:    30
    property bool   autoArchive: true

    // DSP & Réception
    property bool   aptAutoEnabled:      true
    property bool   qrnBlankerEnabled:   false
    property bool   hfConditionerEnabled: false
    property bool   autoMargeEnabled:    true
    property bool   fftNotchEnabled:     false
    property bool   tensorFilterEnabled: false
    property bool   binarisationEnabled: false
    property bool   wefaxFilterEnabled:  false
    property bool   autoSaveEnabled:     true
    property bool   overlayDept06:       false
    property bool   overlayDept83:       false
    property string imageFormat:         "PNG"   // "PNG" ou "JPEG"
    property int    jpegQuality:         90

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onPrefsLoaded(prefs) {
            // Profil opérateur
            if (prefs.callsign)       root.callsign   = prefs.callsign
            if (prefs.qth)            root.qth        = prefs.qth
            if (prefs.locator)        root.locator    = prefs.locator
            if (prefs.assoc)          root.assoc      = prefs.assoc
            // Interface
            if (prefs.ui_mode)        root.uiMode     = prefs.ui_mode
            if (prefs.workspace_dir)  root.workspaceDir = prefs.workspace_dir
            if (prefs.archive_dir)    root.archiveDir = prefs.archive_dir
            if (prefs.keep_days !== undefined) root.keepDays = prefs.keep_days
            // DSP toggles
            if (prefs.apt_auto_enabled       !== undefined) root.aptAutoEnabled       = prefs.apt_auto_enabled
            if (prefs.qrn_blanker_enabled     !== undefined) root.qrnBlankerEnabled    = prefs.qrn_blanker_enabled
            if (prefs.hf_conditioner_enabled  !== undefined) root.hfConditionerEnabled = prefs.hf_conditioner_enabled
            if (prefs.auto_marge_enabled      !== undefined) root.autoMargeEnabled     = prefs.auto_marge_enabled
            if (prefs.fft_notch_enabled       !== undefined) root.fftNotchEnabled      = prefs.fft_notch_enabled
            if (prefs.tensor_filter_enabled   !== undefined) root.tensorFilterEnabled  = prefs.tensor_filter_enabled
            if (prefs.binarisation_enabled    !== undefined) root.binarisationEnabled  = prefs.binarisation_enabled
            if (prefs.wefax_filter_enabled    !== undefined) root.wefaxFilterEnabled   = prefs.wefax_filter_enabled
            if (prefs.auto_save_enabled       !== undefined) root.autoSaveEnabled      = prefs.auto_save_enabled
            if (prefs.overlay_dept06_enabled  !== undefined) root.overlayDept06        = prefs.overlay_dept06_enabled
            if (prefs.overlay_dept83_enabled  !== undefined) root.overlayDept83        = prefs.overlay_dept83_enabled
            if (prefs.image_format)           root.imageFormat  = prefs.image_format
            if (prefs.jpeg_quality !== undefined) root.jpegQuality = prefs.jpeg_quality
        }
    }

    Component.onCompleted: appBridge.loadPrefs()

    // ── Mise en page principale ──────────────────────────────────────────────
    RowLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── Barre latérale de navigation ──────────────────────────────────
        Rectangle {
            Layout.preferredWidth: 180
            Layout.fillHeight: true
            color: T.Theme.bgPanel
            radius: T.Theme.radiusMd
            border.color: T.Theme.border

            ColumnLayout {
                anchors { fill: parent; margins: T.Theme.spacing }
                spacing: 4

                Text {
                    text: "PARAMÈTRES"
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                    font.letterSpacing: 1
                    topPadding: 4
                    bottomPadding: 4
                }

                Repeater {
                    model: [
                        { icon: "📡", lbl: "Profil opérateur" },
                        { icon: "🖥",  lbl: "Interface" },
                        { icon: "⚙️", lbl: "DSP & Réception" },
                        { icon: "📂", lbl: "Espace de travail" },
                        { icon: "🗄",  lbl: "Archives" },
                        { icon: "🔧", lbl: "Diagnostic" }
                    ]
                    delegate: Rectangle {
                        Layout.fillWidth: true
                        height: 36
                        radius: T.Theme.radiusSm
                        color:  root.activeSection === index ? Qt.rgba(0.14, 0.38, 0.92, 0.2) : "transparent"
                        border.color: root.activeSection === index ? T.Theme.accentBorder : "transparent"

                        HoverHandler { id: navH }
                        Rectangle {
                            anchors.fill: parent; radius: parent.radius; color: "white"
                            opacity: navH.hovered && root.activeSection !== index ? 0.04 : 0
                        }

                        RowLayout {
                            anchors { fill: parent; leftMargin: 10 }
                            spacing: 8

                            Text { text: modelData.icon; font.pixelSize: 14 }
                            Text {
                                text: modelData.lbl
                                color: root.activeSection === index ? T.Theme.accent : T.Theme.textMuted
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeSm
                                font.bold: root.activeSection === index
                            }
                        }

                        TapHandler { onTapped: root.activeSection = index }
                    }
                }

                Item { Layout.fillHeight: true }

                // Bouton Enregistrer
                C.FlatButton {
                    Layout.fillWidth: true
                    text:   "💾 Enregistrer"
                    accent: true
                    onClicked: savePrefs()
                }

                // Switch UI (bouton proéminent)
                C.FlatButton {
                    Layout.fillWidth: true
                    text:   root.uiMode === "qt" ? "→ Basculer vers Tkinter" : "→ Basculer vers Qt"
                    accent: false
                    onClicked: switchUiMode()
                }
            }
        }

        // ── Contenu de section ────────────────────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: T.Theme.bgPanel
            radius: T.Theme.radiusMd
            border.color: T.Theme.border

            StackLayout {
                anchors { fill: parent; margins: T.Theme.spacingLg }
                currentIndex: root.activeSection

                // ══ 0 : Profil opérateur ══════════════════════════════════
                ColumnLayout {
                    spacing: T.Theme.spacing

                    Text { text: "PROFIL OPÉRATEUR"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    component Field: RowLayout {
                        property string label: ""
                        property alias  value: fld.text
                        property string ph:    ""
                        Layout.fillWidth: true
                        Text { text: label; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 120 }
                        C.TextInput { id: fld; Layout.fillWidth: true; placeholder: ph; fontFamily: T.Theme.fontMono }
                    }

                    Field { label: "Indicatif :";  value: root.callsign; ph: "F4NMK";  onValueChanged: root.callsign = value }
                    Field { label: "QTH :";         value: root.qth;      ph: "Le Cannet"; onValueChanged: root.qth = value }
                    Field { label: "Locator :";     value: root.locator;  ph: "JN33ls"; onValueChanged: root.locator = value }
                    Field { label: "Association :"; value: root.assoc;    ph: "ADRASEC 06"; onValueChanged: root.assoc = value }

                    Text { text: "Continent :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                    C.DropDown {
                        model: ["EU", "NA", "SA", "AF", "AS", "OC"]
                        currentText: root.continent
                        onSelected: (txt) => root.continent = txt
                    }

                    Item { Layout.fillHeight: true }
                }

                // ══ 1 : Interface ════════════════════════════════════════
                ColumnLayout {
                    spacing: T.Theme.spacing

                    Text { text: "PRÉFÉRENCES D'INTERFACE"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    // Choix de l'interface
                    Text { text: "Interface au démarrage :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }

                    RowLayout {
                        spacing: T.Theme.spacing

                        Repeater {
                            model: [
                                { val: "qt", lbl: "Qt (moderne)", desc: "Interface Qt/QML\nFluidité et performances" },
                                { val: "tk", lbl: "Tkinter (classique)", desc: "Interface originale\nCompatibilité maximale" }
                            ]
                            delegate: Rectangle {
                                Layout.preferredWidth: 200
                                height: 70
                                radius: T.Theme.radiusMd
                                color: root.uiMode === modelData.val ? Qt.rgba(0.14, 0.38, 0.92, 0.15) : T.Theme.bgSurface
                                border.color: root.uiMode === modelData.val ? T.Theme.accentBorder : T.Theme.border

                                Column {
                                    anchors { fill: parent; margins: 10 }
                                    spacing: 4

                                    Text {
                                        text: modelData.lbl
                                        color: root.uiMode === modelData.val ? T.Theme.accent : T.Theme.textPrimary
                                        font.family: T.Theme.fontMono
                                        font.pixelSize: T.Theme.fontSizeSm
                                        font.bold: root.uiMode === modelData.val
                                    }
                                    Text {
                                        text: modelData.desc
                                        color: T.Theme.textDim
                                        font.family: T.Theme.fontMono
                                        font.pixelSize: T.Theme.fontSizeXs
                                        lineHeight: 1.3
                                    }
                                }

                                TapHandler { onTapped: root.uiMode = modelData.val }
                            }
                        }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: T.Theme.border }

                    // Autres options
                    component Toggle: RowLayout {
                        property string label: ""
                        property alias  value: tog.on
                        Layout.fillWidth: true

                        Text { text: label; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.fillWidth: true }
                        Rectangle {
                            id: tog
                            property bool on: false
                            width: 36; height: 18; radius: 9
                            color: on ? T.Theme.accent : T.Theme.bgSurface
                            border.color: on ? T.Theme.accentBorder : T.Theme.border

                            Rectangle {
                                x: parent.on ? parent.width - 15 : 3
                                y: 3; width: 12; height: 12; radius: 6
                                color: parent.on ? "white" : T.Theme.textDim
                                Behavior on x { NumberAnimation { duration: 150 } }
                            }
                            TapHandler { onTapped: parent.on = !parent.on }
                        }
                    }

                    Toggle { label: "Démarrer audio automatiquement";       value: root.startAudioAuto; onValueChanged: root.startAudioAuto = value }
                    Toggle { label: "Mode compact (réduire marges)";         value: root.compactMode;    onValueChanged: root.compactMode = value }

                    Item { Layout.fillHeight: true }
                }

                // ══ 2 : DSP & Réception ════════════════════════════════
                ColumnLayout {
                    spacing: 4

                    Text { text: "DSP & RÉCEPTION"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1; bottomPadding: 4 }

                    // Composant Toggle local réutilisable
                    component DspToggle: RowLayout {
                        property string label: ""
                        property string tip:   ""
                        property alias  value: sw.on
                        Layout.fillWidth: true
                        spacing: 8

                        Column {
                            Layout.fillWidth: true
                            spacing: 1
                            Text { text: label; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                            Text { text: tip; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; visible: tip !== "" }
                        }
                        Rectangle {
                            id: sw
                            property bool on: false
                            width: 36; height: 18; radius: 9
                            color: on ? T.Theme.accent : T.Theme.bgSurface
                            border.color: on ? T.Theme.accentBorder : T.Theme.border
                            Rectangle {
                                x: parent.on ? parent.width - 15 : 3; y: 3; width: 12; height: 12; radius: 6
                                color: parent.on ? "white" : T.Theme.textDim
                                Behavior on x { NumberAnimation { duration: 150 } }
                            }
                            TapHandler { onTapped: parent.on = !parent.on }
                        }
                    }

                    // ── Réception automatique ──────────────────────────────
                    Text { text: "RÉCEPTION AUTOMATIQUE"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; topPadding: 4 }

                    DspToggle {
                        label: "Détection APT auto"
                        tip:   "Détecte les signaux 300 Hz (start) et 450 Hz (stop)"
                        value: root.aptAutoEnabled
                        onValueChanged: { root.aptAutoEnabled = value; appBridge.setAptAutoEnabled(value) }
                    }
                    DspToggle {
                        label: "Sauvegarde automatique"
                        tip:   "Enregistre chaque carte à la fin de réception"
                        value: root.autoSaveEnabled
                        onValueChanged: { root.autoSaveEnabled = value; appBridge.setAutoSavePngEnabled(value) }
                    }
                    DspToggle {
                        label: "Auto-marge (recadrage)"
                        tip:   "Aligne automatiquement le bord gauche de la carte"
                        value: root.autoMargeEnabled
                        onValueChanged: { root.autoMargeEnabled = value; appBridge.setAutoMargeEnabled(value) }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: T.Theme.border }

                    // ── Filtres DSP ──────────────────────────────────────
                    Text { text: "FILTRES DSP"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; topPadding: 4 }

                    DspToggle {
                        label: "Filtre passe-bande WEFAX"
                        tip:   "Butterworth 6e ordre [1400–2400 Hz]"
                        value: root.wefaxFilterEnabled
                        onValueChanged: { root.wefaxFilterEnabled = value; dsp.setWefaxFilterEnabled(value) }
                    }
                    DspToggle {
                        label: "QRN Blanker"
                        tip:   "Élimine les impulsions parasites courtes (statique)"
                        value: root.qrnBlankerEnabled
                        onValueChanged: { root.qrnBlankerEnabled = value; appBridge.setQrnBlankerEnabled(value) }
                    }
                    DspToggle {
                        label: "Conditionneur HF"
                        tip:   "Égalise le spectre reçu (propagation HF)"
                        value: root.hfConditionerEnabled
                        onValueChanged: { root.hfConditionerEnabled = value; appBridge.setHfConditionerEnabled(value) }
                    }
                    DspToggle {
                        label: "FFT Notch (raies parasites)"
                        tip:   "Détecte et supprime les raies continues fixes"
                        value: root.fftNotchEnabled
                        onValueChanged: { root.fftNotchEnabled = value; appBridge.setFftNotchEnabled(value) }
                    }
                    DspToggle {
                        label: "Filtre tensor (IA)"
                        tip:   "Réduction de bruit par réseau de neurones"
                        value: root.tensorFilterEnabled
                        onValueChanged: { root.tensorFilterEnabled = value; appBridge.setTensorFilterEnabled(value) }
                    }
                    DspToggle {
                        label: "Binarisation post-traitement"
                        tip:   "Convertit en noir/blanc pur (radar/synoptique)"
                        value: root.binarisationEnabled
                        onValueChanged: { root.binarisationEnabled = value; appBridge.setBinarisationEnabled(value) }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: T.Theme.border }

                    // ── Format image (un seul fichier par carte) ──────────
                    Text { text: "FORMAT IMAGE SAUVEGARDÉ"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; topPadding: 4 }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Repeater {
                            model: [
                                { val: "PNG",  lbl: "PNG",  desc: "Sans perte\n~200–600 kB" },
                                { val: "JPEG", lbl: "JPEG", desc: "Winlink/VARA\n~40–80 kB" }
                            ]
                            delegate: Rectangle {
                                Layout.preferredWidth: 110
                                height: 52
                                radius: T.Theme.radiusMd
                                color: root.imageFormat === modelData.val ? Qt.rgba(0.14, 0.38, 0.92, 0.15) : T.Theme.bgSurface
                                border.color: root.imageFormat === modelData.val ? T.Theme.accentBorder : T.Theme.border
                                Column {
                                    anchors { fill: parent; margins: 8 }
                                    spacing: 2
                                    Text { text: modelData.lbl; color: root.imageFormat === modelData.val ? T.Theme.accent : T.Theme.textPrimary; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; font.bold: root.imageFormat === modelData.val }
                                    Text { text: modelData.desc; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; lineHeight: 1.3 }
                                }
                                TapHandler { onTapped: { root.imageFormat = modelData.val; appBridge.setImageFormat(modelData.val) } }
                            }
                        }
                    }

                    // Qualité JPEG (visible si JPEG sélectionné)
                    RowLayout {
                        Layout.fillWidth: true
                        visible: root.imageFormat === "JPEG"
                        spacing: 8
                        Text { text: "Qualité JPEG :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 110 }
                        C.DropDown {
                            model: ["70", "80", "85", "90", "95"]
                            currentText: String(root.jpegQuality)
                            onSelected: (txt) => { root.jpegQuality = parseInt(txt); appBridge.setJpegQuality(parseInt(txt)) }
                        }
                        Text { text: "(Winlink : 85 recommandé)"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs }
                    }

                    Rectangle { Layout.fillWidth: true; height: 1; color: T.Theme.border }

                    // ── Overlays cartographiques ─────────────────────────
                    Text { text: "OVERLAYS CARTOGRAPHIQUES"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; topPadding: 4 }

                    DspToggle {
                        label: "Overlay dept 06 (Alpes-Maritimes)"
                        tip:   "Superpose les limites du département 06"
                        value: root.overlayDept06
                        onValueChanged: { root.overlayDept06 = value; appBridge.setOverlayDept06Enabled(value) }
                    }
                    DspToggle {
                        label: "Overlay dept 83 (Var)"
                        tip:   "Superpose les limites du département 83"
                        value: root.overlayDept83
                        onValueChanged: { root.overlayDept83 = value; appBridge.setOverlayDept83Enabled(value) }
                    }

                    Item { Layout.fillHeight: true }
                }

                // ══ 3 : Espace de travail ════════════════════════════════
                ColumnLayout {
                    spacing: T.Theme.spacing

                    Text { text: "ESPACE DE TRAVAIL"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Dossier :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 80 }
                        C.TextInput {
                            Layout.fillWidth: true
                            text: root.workspaceDir
                            placeholder: "~/Documents/WEFAX"
                            fontFamily: T.Theme.fontMono
                            onTextChanged: (t) => root.workspaceDir = t
                        }
                        C.FlatButton { text: "📂"; accent: false; implicitWidth: 32; onClicked: appBridge.chooseWorkspaceDir() }
                    }

                    C.FlatButton {
                        text: "Ouvrir le dossier"
                        accent: false
                        onClicked: appBridge.openWorkspace()
                    }

                    Item { Layout.fillHeight: true }
                }

                // ══ 3 : Archives ════════════════════════════════════════
                ColumnLayout {
                    spacing: T.Theme.spacing

                    Text { text: "ARCHIVES"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Dossier archives :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 120 }
                        C.TextInput {
                            Layout.fillWidth: true
                            text: root.archiveDir
                            placeholder: "~/Documents/WEFAX/archives"
                            fontFamily: T.Theme.fontMono
                            onTextChanged: (t) => root.archiveDir = t
                        }
                        C.FlatButton { text: "📂"; accent: false; implicitWidth: 32; onClicked: appBridge.chooseArchiveDir() }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Conserver (jours) :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.preferredWidth: 140 }
                        C.DropDown {
                            model: ["7", "14", "30", "60", "90", "365"]
                            currentText: String(root.keepDays)
                            onSelected: (txt) => root.keepDays = parseInt(txt)
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Text { text: "Archivage automatique :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.fillWidth: true }
                        Rectangle {
                            property bool on: root.autoArchive
                            width: 36; height: 18; radius: 9
                            color: on ? T.Theme.accent : T.Theme.bgSurface
                            border.color: on ? T.Theme.accentBorder : T.Theme.border
                            Rectangle {
                                x: parent.on ? parent.width - 15 : 3; y: 3; width: 12; height: 12; radius: 6
                                color: parent.on ? "white" : T.Theme.textDim
                                Behavior on x { NumberAnimation { duration: 150 } }
                            }
                            TapHandler { onTapped: { parent.on = !parent.on; root.autoArchive = parent.on } }
                        }
                    }

                    C.FlatButton { text: "🗄 Ouvrir les archives"; accent: false; onClicked: appBridge.openArchives() }

                    Item { Layout.fillHeight: true }
                }

                // ══ 4 : Diagnostic ══════════════════════════════════════
                ColumnLayout {
                    spacing: T.Theme.spacing

                    Text { text: "DIAGNOSTIC"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs; font.letterSpacing: 1 }

                    RowLayout {
                        spacing: T.Theme.spacing
                        C.FlatButton { text: "🔍 Test CI-V";      accent: false; Layout.fillWidth: true; onClicked: appBridge.runDiagnostic("civ") }
                        C.FlatButton { text: "🔊 Test Audio";      accent: false; Layout.fillWidth: true; onClicked: appBridge.runDiagnostic("audio") }
                        C.FlatButton { text: "📡 Test Fréquence";  accent: false; Layout.fillWidth: true; onClicked: appBridge.runDiagnostic("freq") }
                    }

                    // Sortie diagnostic
                    C.LogView {
                        id: diagLog
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                    }

                    Connections {
                        target: appBridge
                        function onDiagnosticLine(text) { diagLog.append(text) }
                    }
                }
            }
        }
    }

    // ── Fonctions locales ────────────────────────────────────────────────────
    function savePrefs() {
        appBridge.savePrefs({
            // Profil opérateur
            callsign:        root.callsign,
            qth:             root.qth,
            locator:         root.locator,
            assoc:           root.assoc,
            continent:       root.continent,
            // Interface
            ui_mode:         root.uiMode,
            start_audio_auto: root.startAudioAuto,
            compact_mode:    root.compactMode,
            workspace_dir:   root.workspaceDir,
            // Archives
            archive_dir:     root.archiveDir,
            keep_days:       root.keepDays,
            auto_archive:    root.autoArchive,
            // DSP & Réception
            apt_auto_enabled:        root.aptAutoEnabled,
            qrn_blanker_enabled:     root.qrnBlankerEnabled,
            hf_conditioner_enabled:  root.hfConditionerEnabled,
            auto_marge_enabled:      root.autoMargeEnabled,
            fft_notch_enabled:       root.fftNotchEnabled,
            tensor_filter_enabled:   root.tensorFilterEnabled,
            binarisation_enabled:    root.binarisationEnabled,
            wefax_filter_enabled:    root.wefaxFilterEnabled,
            auto_save_enabled:       root.autoSaveEnabled,
            overlay_dept06_enabled:  root.overlayDept06,
            overlay_dept83_enabled:  root.overlayDept83,
            // Format image
            image_format:            root.imageFormat,
            jpeg_quality:            root.jpegQuality
        })
    }

    function switchUiMode() {
        const newMode = root.uiMode === "qt" ? "tk" : "qt"
        root.uiMode = newMode
        savePrefs()
        appBridge.switchUiMode(newMode)
    }
}
