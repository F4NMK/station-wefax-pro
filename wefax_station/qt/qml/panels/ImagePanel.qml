import QtQuick
import QtQuick.Layouts
import "../components" as C
import ".." as T

/*
 * ImagePanel.qml — Onglet IMAGE WEFAX (complet)
 *
 * Context properties attendus :
 *   dsp      : DspBridge   (signaux spectrumReady, signalLevelChanged, lineReceived,
 *                            imageCompleted, snrChanged, phaseDetected)
 *   radio    : RadioBridge
 *   appBridge: AppBridge
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    // ── État local ───────────────────────────────────────────────────────────
    property real   snr:         0.0
    property real   phase:       0.0
    property real   signalLevel: 0.0
    property bool   receiving:   false
    property int    linesReceived: 0
    property string displayMode: "TRAITE"      // TRAITE | BRUT | SPLIT
    property bool   fftNotch:    false
    property bool   tensorOn:    true
    property bool   binAdaptive: true
    property real   usbOffset:   1.9
    property real   zoomLevel:   1.0
    property int    imgRotation:    0
    property string imageSource: ""
    property var    spectrumData: []
    property real   progress:    0.0
    property string lastImagePath: ""

    // ── Connexion DSP ────────────────────────────────────────────────────────
    Connections {
        target: dsp
        function onSpectrumReady(data) { root.spectrumData = data; specCanvas.requestPaint() }
        function onSignalLevelChanged(lvl) { root.signalLevel = lvl }
        function onSnrChanged(snr)        { root.snr = snr }
        function onPhaseDetected(ph)      { root.phase = ph }
        function onLineReceived(n, frac) {
            root.linesReceived = n
            root.receiving = true
            root.progress = frac
        }
        function onImageCompleted(path) {
            root.imageSource = "file:///" + path
            root.receiving = false
            root.progress = 1.0
            root.lastImagePath = path
            dspLog.append("✅ Image complète : " + path)
        }
    }

    // ── Mise en page principale ──────────────────────────────────────────────
    ColumnLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacing

        // ── Barre supérieure : métriques + contrôles mode ─────────────────
        RowLayout {
            Layout.fillWidth: true
            spacing: T.Theme.spacing

            // Métriques rapides
            Repeater {
                model: [
                    { lbl: "SNR",    val: root.snr.toFixed(1) + " dB",          ok: root.snr >= 10 },
                    { lbl: "PHASE",  val: root.phase.toFixed(2) + " °",          ok: Math.abs(root.phase) < 15 },
                    { lbl: "NIVEAU", val: (root.signalLevel*100).toFixed(0) + "%", ok: root.signalLevel > 0.3 },
                    { lbl: "LIGNES", val: String(root.linesReceived),             ok: root.receiving }
                ]

                delegate: Rectangle {
                    Layout.preferredWidth: 100
                    height: 44
                    color: T.Theme.bgPanel
                    radius: T.Theme.radiusMd
                    border.color: T.Theme.border

                    Column {
                        anchors.centerIn: parent
                        spacing: 2

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text:  modelData.lbl
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.letterSpacing: 1
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text:  modelData.val
                            color: modelData.ok ? T.Theme.okFg : T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            font.bold: true
                        }
                    }
                }
            }

            Item { Layout.fillWidth: true }

            // Mode d'affichage
            RowLayout {
                spacing: 4

                Text { text: "AFFICHAGE :"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeXs }

                Repeater {
                    model: ["TRAITÉ", "BRUT", "SPLIT"]
                    delegate: C.FlatButton {
                        property string mVal: ["TRAITE", "BRUT", "SPLIT"][index]
                        text:   modelData
                        accent: root.displayMode === mVal
                        onClicked: root.displayMode = mVal
                    }
                }
            }
        }

        // ── Zone principale : spectre + image ─────────────────────────────
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            // ══ PANNEAU GAUCHE : contrôles DSP ══
            ColumnLayout {
                Layout.preferredWidth: 220
                Layout.fillHeight: true
                spacing: T.Theme.spacing

                // ── Réception en cours ────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    height: 50
                    color: T.Theme.bgPanel
                    radius: T.Theme.radiusMd
                    border.color: root.receiving ? T.Theme.accentBorder : T.Theme.border

                    Column {
                        anchors { fill: parent; margins: 8 }
                        spacing: 4

                        Text {
                            text: root.receiving ? "RÉCEPTION EN COURS" : "EN ATTENTE"
                            color: root.receiving ? T.Theme.accent : T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.letterSpacing: 1
                        }

                        // Barre progression
                        Rectangle {
                            width:  parent.width
                            height: 6
                            radius: 3
                            color:  T.Theme.bgSurface

                            Rectangle {
                                width:  parent.width * root.progress
                                height: parent.height
                                radius: parent.radius
                                color:  root.receiving ? T.Theme.accent : T.Theme.textDim

                                Behavior on width { NumberAnimation { duration: 200 } }
                            }
                        }
                    }
                }

                // ── Traitement DSP ────────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    color: T.Theme.bgPanel
                    radius: T.Theme.radiusMd
                    border.color: T.Theme.border
                    height: dspCtrlCol.implicitHeight + 16

                    ColumnLayout {
                        id: dspCtrlCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        spacing: 8

                        Text {
                            text: "TRAITEMENT DSP"
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.letterSpacing: 1
                        }

                        // Toggles
                        Repeater {
                            model: [
                                { lbl: "Notch FFT", prop: "fftNotch" },
                                { lbl: "Tenseur structure", prop: "tensorOn" },
                                { lbl: "Binarisation adaptative", prop: "binAdaptive" }
                            ]
                            delegate: RowLayout {
                                Layout.fillWidth: true

                                Text {
                                    Layout.fillWidth: true
                                    text:  modelData.lbl
                                    color: T.Theme.textMuted
                                    font.family: T.Theme.fontMono
                                    font.pixelSize: T.Theme.fontSizeSm
                                    wrapMode: Text.WordWrap
                                }

                                // Toggle switch
                                Rectangle {
                                    id: tog
                                    property bool on: root[modelData.prop]
                                    width: 36; height: 18; radius: 9
                                    color: on ? T.Theme.accent : T.Theme.bgSurface
                                    border.color: on ? T.Theme.accentBorder : T.Theme.border

                                    Rectangle {
                                        x: parent.on ? parent.width - 15 : 3
                                        y: 3; width: 12; height: 12; radius: 6
                                        color: parent.on ? "white" : T.Theme.textDim
                                        Behavior on x { NumberAnimation { duration: 150 } }
                                    }

                                    TapHandler {
                                        onTapped: {
                                            root[modelData.prop] = !root[modelData.prop]
                                            dsp.setDspParam(modelData.prop, root[modelData.prop])
                                        }
                                    }
                                }
                            }
                        }

                        // Offset USB
                        Text { text: "Offset USB :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4

                            // Slider USB custom (Item + MouseArea, pas de QQC pour éviter warnings Windows)
                            Item {
                                id: usbSlider
                                Layout.fillWidth: true
                                implicitHeight: 20

                                property real sliderFrom:  1.5
                                property real sliderTo:    2.5
                                property real sliderStep:  0.05
                                property real sliderValue: root.usbOffset
                                property real visualPos:   (sliderValue - sliderFrom) / (sliderTo - sliderFrom)

                                // Track
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: 0; width: parent.width; height: 4; radius: 2
                                    color: T.Theme.bgSurface
                                    Rectangle {
                                        width: parent.width * usbSlider.visualPos
                                        height: parent.height; radius: parent.radius
                                        color: T.Theme.accent
                                    }
                                }
                                // Handle
                                Rectangle {
                                    anchors.verticalCenter: parent.verticalCenter
                                    x: usbSlider.visualPos * (usbSlider.width - width)
                                    width: 14; height: 14; radius: 7
                                    color: T.Theme.accent
                                    border.color: T.Theme.bgRoot; border.width: 2
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    function updateVal(mx) {
                                        const frac = Math.max(0, Math.min(1, mx / usbSlider.width))
                                        const v = usbSlider.sliderFrom + frac * (usbSlider.sliderTo - usbSlider.sliderFrom)
                                        const stepped = Math.round(v / usbSlider.sliderStep) * usbSlider.sliderStep
                                        usbSlider.sliderValue = stepped
                                        root.usbOffset = stepped
                                        dsp.setDspParam("usbOffset", stepped)
                                    }
                                    onClicked: (mouse) => updateVal(mouse.x)
                                    onPositionChanged: (mouse) => { if (pressed) updateVal(mouse.x) }
                                }
                            }

                            Text {
                                text: root.usbOffset.toFixed(2)
                                color: T.Theme.textPrimary
                                font.family: T.Theme.fontMono
                                font.pixelSize: T.Theme.fontSizeSm
                                Layout.preferredWidth: 36
                            }
                        }
                    }
                }

                // ── Rotation + Zoom ───────────────────────────────────────
                Rectangle {
                    Layout.fillWidth: true
                    color: T.Theme.bgPanel
                    radius: T.Theme.radiusMd
                    border.color: T.Theme.border
                    height: imgCtrlCol.implicitHeight + 16

                    ColumnLayout {
                        id: imgCtrlCol
                        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 8 }
                        spacing: 8

                        Text {
                            text: "AFFICHAGE IMAGE"
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                            font.letterSpacing: 1
                        }

                        // Rotation
                        Text { text: "Rotation :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                        RowLayout {
                            Layout.fillWidth: true
                            Repeater {
                                model: [{ lbl: "0°", val: 0 }, { lbl: "90°", val: 90 }, { lbl: "180°", val: 180 }, { lbl: "270°", val: 270 }]
                                delegate: C.FlatButton {
                                    text:   modelData.lbl
                                    accent: root.imgRotation === modelData.val
                                    Layout.fillWidth: true
                                    onClicked: root.imgRotation = modelData.val
                                }
                            }
                        }

                        // Zoom
                        Text { text: "Zoom :"; color: T.Theme.textMuted; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm }
                        RowLayout {
                            Layout.fillWidth: true
                            Repeater {
                                model: [{ lbl: "×1", val: 1.0 }, { lbl: "×2", val: 2.0 }, { lbl: "FIT", val: -1.0 }]
                                delegate: C.FlatButton {
                                    text:   modelData.lbl
                                    accent: modelData.val > 0 && root.zoomLevel === modelData.val
                                    Layout.fillWidth: true
                                    onClicked: root.zoomLevel = modelData.val
                                }
                            }
                        }

                        // Actions image
                        C.FlatButton {
                            text: "💾 Sauvegarder"
                            Layout.fillWidth: true
                            accent: false
                            enabled: root.lastImagePath !== ""
                            onClicked: appBridge.saveCurrentImage(root.lastImagePath)
                        }
                        C.FlatButton {
                            text: "📂 Archives"
                            Layout.fillWidth: true
                            accent: false
                            onClicked: appBridge.openArchives()
                        }
                    }
                }

                Item { Layout.fillHeight: true }

                // Log DSP
                C.LogView {
                    id: dspLog
                    Layout.fillWidth: true
                    Layout.preferredHeight: 120
                }
            }

            // ══ PANNEAU DROIT : spectre + image ══
            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: T.Theme.spacing

                // Spectre audio
                Rectangle {
                    Layout.fillWidth: true
                    height: 100
                    color: T.Theme.bgCanvas
                    radius: T.Theme.radiusMd
                    border.color: T.Theme.border
                    clip: true

                    Canvas {
                        id: specCanvas
                        anchors { fill: parent; margins: 1 }

                        onPaint: {
                            const ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            ctx.fillStyle = T.Theme.bgCanvas
                            ctx.fillRect(0, 0, width, height)

                            const data = root.spectrumData
                            if (!data || data.length === 0) return

                            const step = width / data.length
                            ctx.fillStyle = T.Theme.accent
                            ctx.globalAlpha = 0.8

                            for (let i = 0; i < data.length; i++) {
                                const val = Math.max(0, Math.min(1, data[i]))
                                const h   = val * height
                                ctx.fillRect(i * step, height - h, Math.max(1, step - 1), h)
                            }

                            // Repères fréquences WEFAX (1500-2800 Hz en USB)
                            ctx.strokeStyle = "#ff4444"
                            ctx.lineWidth   = 1
                            ctx.globalAlpha = 0.5
                            ;[1900, 2300].forEach(hz => {
                                const x = (hz / 3000) * width
                                ctx.beginPath()
                                ctx.moveTo(x, 0)
                                ctx.lineTo(x, height)
                                ctx.stroke()
                            })
                            ctx.globalAlpha = 1
                        }
                    }

                    Text {
                        anchors { left: parent.left; leftMargin: 8; bottom: parent.bottom; bottomMargin: 4 }
                        text: "SPECTRE AUDIO — 0 … 3 kHz"
                        color: T.Theme.textDim
                        font.family: T.Theme.fontMono
                        font.pixelSize: T.Theme.fontSizeXs
                    }
                }

                // Image principale
                Rectangle {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    color: T.Theme.bgCanvas
                    radius: T.Theme.radiusMd
                    border.color: T.Theme.border
                    clip: true

                    // Placeholder si pas d'image
                    Column {
                        anchors.centerIn: parent
                        spacing: T.Theme.spacing
                        visible: root.imageSource === ""

                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "〰"
                            color: T.Theme.textDim
                            font.pixelSize: 48
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "En attente d'une image WEFAX…"
                            color: T.Theme.textDim
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                        }
                    }

                    // Image reçue
                    Image {
                        id: wefaxImage
                        anchors.centerIn: parent
                        source:          root.imageSource
                        fillMode:        root.zoomLevel < 0 ? Image.PreserveAspectFit : Image.Pad
                        width:           root.zoomLevel < 0 ? parent.width  : sourceSize.width  * root.zoomLevel
                        height:          root.zoomLevel < 0 ? parent.height : sourceSize.height * root.zoomLevel
                        rotation:        root.imgRotation
                        smooth:          true
                        visible:         root.imageSource !== ""
                    }

                    // Info image (en bas)
                    Rectangle {
                        anchors { left: parent.left; right: parent.right; bottom: parent.bottom }
                        height: 24
                        color: Qt.rgba(0,0,0,0.5)
                        visible: root.imageSource !== ""

                        Text {
                            anchors { left: parent.left; leftMargin: 8; verticalCenter: parent.verticalCenter }
                            text: root.receiving ?
                                  ("Réception : " + root.linesReceived + " lignes — " + (root.progress*100).toFixed(0) + "%") :
                                  ("Image : " + root.lastImagePath.split("/").pop())
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeXs
                        }
                    }
                }
            }
        }
    }

}
