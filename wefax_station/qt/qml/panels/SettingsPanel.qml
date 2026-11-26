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

    // ── Connexion aux ponts ──────────────────────────────────────────────────
    Connections {
        target: appBridge
        function onPrefsLoaded(prefs) {
            if (prefs.callsign)       root.callsign   = prefs.callsign
            if (prefs.qth)            root.qth        = prefs.qth
            if (prefs.locator)        root.locator    = prefs.locator
            if (prefs.assoc)          root.assoc      = prefs.assoc
            if (prefs.ui_mode)        root.uiMode     = prefs.ui_mode
            if (prefs.workspace_dir)  root.workspaceDir = prefs.workspace_dir
            if (prefs.archive_dir)    root.archiveDir = prefs.archive_dir
            if (prefs.keep_days !== undefined) root.keepDays = prefs.keep_days
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

                // ══ 2 : Espace de travail ════════════════════════════════
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
            callsign:        root.callsign,
            qth:             root.qth,
            locator:         root.locator,
            assoc:           root.assoc,
            continent:       root.continent,
            ui_mode:         root.uiMode,
            start_audio_auto: root.startAudioAuto,
            compact_mode:    root.compactMode,
            workspace_dir:   root.workspaceDir,
            archive_dir:     root.archiveDir,
            keep_days:       root.keepDays,
            auto_archive:    root.autoArchive
        })
    }

    function switchUiMode() {
        const newMode = root.uiMode === "qt" ? "tk" : "qt"
        root.uiMode = newMode
        savePrefs()
        appBridge.switchUiMode(newMode)
    }
}
