import QtQuick
import QtQuick.Controls
import ".." as T

/*
 * LogView.qml — Console de log défilante, style terminal
 *
 * Usage :
 *   LogView { id: log }
 *   log.append("2026-11-25 14:30:01  CI-V handshake OK")
 */
Rectangle {
    id: root

    color:  T.Theme.bgCanvas
    radius: T.Theme.radiusSm
    clip:   true

    property int maxLines: 500
    property alias count: listView.count

    // ── Modèle ──────────────────────────────────────────────────────────
    ListModel { id: logModel }

    function append(text) {
        // Découpe en lignes si nécessaire
        const lines = text.split("\n")
        for (const l of lines) {
            if (l.trim() === "") continue
            if (logModel.count >= maxLines) logModel.remove(0)
            logModel.append({ "line": l })
        }
        Qt.callLater(() => listView.positionViewAtEnd())
    }

    function clear() { logModel.clear() }

    // ── Vue liste ───────────────────────────────────────────────────────
    ListView {
        id: listView
        anchors { fill: parent; margins: 4 }
        model: logModel
        clip:  true

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }

        delegate: Text {
            width: listView.width
            text:  model.line
            color: {
                const l = model.line.toLowerCase()
                if (l.includes("erreur") || l.includes("error") || l.includes("fail"))
                    return T.Theme.errFg
                if (l.includes("attention") || l.includes("warn"))
                    return T.Theme.warnFg
                if (l.includes("ok") || l.includes("connecté") || l.includes("success"))
                    return T.Theme.okFg
                return T.Theme.textMuted
            }
            font.family:  T.Theme.fontMono
            font.pixelSize: T.Theme.fontSizeXs
            wrapMode: Text.NoWrap
            elide:    Text.ElideRight
        }
    }
}
