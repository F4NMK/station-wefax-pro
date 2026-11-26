import QtQuick
import QtQuick.Layouts
import "../components" as C
import ".." as T

/*
 * ImagePanel.qml — Onglet IMAGE (WEFAX)
 *
 * Context properties attendus :
 *   dsp : DspBridge  (signaux spectrumReady, signalLevelChanged, lineReceived, imageCompleted, snrChanged, phaseDetected)
 */
Rectangle {
    id: root
    color: T.Theme.bgRoot

    property real   snr:         0.0
    property string phase:       "---"
    property real   signalLevel: 0.0
    property string lastImagePath: ""

    Connections {
        target: dsp
        function onSnrChanged(val)       { root.snr = val }
        function onPhaseDetected(ph)     { root.phase = ph }
        function onSignalLevelChanged(l) { root.signalLevel = l }
        function onImageCompleted(path)  {
            root.lastImagePath = path
            imageView.source = "file:///" + path
            dspLog.append("Image complète : " + path)
        }
        function onLineReceived(lineNum, _data) {
            progressBar.value = Math.min(lineNum / 1200, 1.0)
        }
        function onSpectrumReady(bins) {
            spectrumCanvas.bins = bins
            spectrumCanvas.requestPaint()
        }
    }

    RowLayout {
        anchors { fill: parent; margins: T.Theme.spacingLg }
        spacing: T.Theme.spacingLg

        // ── Colonne gauche : paramètres DSP ────────────────────────────
        ColumnLayout {
            Layout.preferredWidth: 220
            Layout.fillHeight: true
            spacing: T.Theme.spacing

            // Métriques qualité
            Rectangle {
                Layout.fillWidth: true
                height: 110
                color: T.Theme.bgPanel
                radius: T.Theme.radiusMd
                border.color: T.Theme.border

                Column {
                    anchors { fill: parent; margins: T.Theme.spacing }
                    spacing: T.Theme.spacing

                    // SNR
                    RowLayout {
                        width: parent.width
                        Text { text: "SNR"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.fillWidth: true }
                        Text {
                            text: root.snr.toFixed(1) + " dB"
                            color: root.snr >= 10 ? T.Theme.okFg : (root.snr >= 5 ? T.Theme.warnFg : T.Theme.errFg)
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                            font.bold: true
                        }
                    }

                    // Phase
                    RowLayout {
                        width: parent.width
                        Text { text: "PHASE"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.fillWidth: true }
                        Text {
                            text: root.phase
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                        }
                    }

                    // Niveau signal
                    RowLayout {
                        width: parent.width
                        Text { text: "NIVEAU"; color: T.Theme.textDim; font.family: T.Theme.fontMono; font.pixelSize: T.Theme.fontSizeSm; Layout.fillWidth: true }
                        Text {
                            text: (root.signalLevel * 100).toFixed(0) + "%"
                            color: T.Theme.textPrimary
                            font.family: T.Theme.fontMono
                            font.pixelSize: T.Theme.fontSizeSm
                        }
                    }
                }
            }

            // Spectre audio (canvas)
            Rectangle {
                Layout.fillWidth: true
                height: 100
                color: T.Theme.bgCanvas
                radius: T.Theme.radiusSm

                Text {
                    anchors { top: parent.top; left: parent.left; margins: 4 }
                    text: "SPECTRE"
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                }

                Canvas {
                    id: spectrumCanvas
                    anchors { fill: parent; topMargin: 16; margins: 4 }
                    property var bins: []

                    onPaint: {
                        const ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        if (!bins || bins.length === 0) return

                        const w = width / bins.length
                        ctx.fillStyle = "#2563eb"
                        for (let i = 0; i < bins.length; i++) {
                            const h = bins[i] * height
                            ctx.fillRect(i * w, height - h, Math.max(w - 1, 1), h)
                        }
                    }
                }
            }

            // Progression ligne en cours
            ColumnLayout {
                Layout.fillWidth: true
                spacing: 4

                Text {
                    text: "RÉCEPTION EN COURS"
                    color: T.Theme.textDim
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                    font.letterSpacing: 1
                }

                // Barre de progression maison (évite le warning de style natif)
                Item {
                    id: progressBar
                    Layout.fillWidth: true
                    height: 8
                    property real value: 0.0

                    Rectangle {
                        anchors.fill: parent
                        color:  T.Theme.bgCanvas
                        radius: 2
                    }
                    Rectangle {
                        width:  parent.value * parent.width
                        height: parent.height
                        radius: 2
                        color:  T.Theme.accent
                        Behavior on width { NumberAnimation { duration: 80 } }
                    }
                }

                Text {
                    text: (progressBar.value * 100).toFixed(0) + "%"
                    color: T.Theme.textMuted
                    font.family: T.Theme.fontMono
                    font.pixelSize: T.Theme.fontSizeXs
                }
            }

            // Log DSP
            C.LogView {
                id: dspLog
                Layout.fillWidth: true
                Layout.fillHeight: true
            }
        }

        // ── Colonne droite : image WEFAX ───────────────────────────────
        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: T.Theme.bgCanvas
            radius: T.Theme.radiusMd
            border.color: T.Theme.border
            clip: true

            // Placeholder
            Text {
                visible: root.lastImagePath === ""
                anchors.centerIn: parent
                text: "En attente d'image WEFAX…"
                color: T.Theme.textDim
                font.family: T.Theme.fontMono
                font.pixelSize: T.Theme.fontSizeMd
            }

            Image {
                id: imageView
                anchors.fill: parent
                fillMode: Image.PreserveAspectFit
                smooth: true
                visible: root.lastImagePath !== ""
            }

            // Nom du fichier en superposition
            Text {
                visible: root.lastImagePath !== ""
                anchors { bottom: parent.bottom; left: parent.left; margins: 6 }
                text: root.lastImagePath.split("/").pop()
                color: T.Theme.textDim
                font.family: T.Theme.fontMono
                font.pixelSize: T.Theme.fontSizeXs
            }
        }
    }
}
