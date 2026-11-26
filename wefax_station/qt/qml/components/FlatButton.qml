import QtQuick
import QtQuick.Layouts
import ".." as T

/*
 * FlatButton.qml — Bouton entièrement dessiné en QML, sans dépendance
 * au style natif de la plateforme (évite les warnings Windows/macOS
 * "current style does not support customization").
 *
 * Propriétés :
 *   text        : string   — libellé
 *   enabled     : bool     — grisé si false
 *   accent      : bool     — style "accent" (bleu) si true, "outline" si false
 *   onClicked   : signal   — slot JS appelé au clic
 */
Rectangle {
    id: root

    property string  text:   ""
    property bool    accent: true
    signal clicked()
    // 'enabled' est hérité de Item — pas besoin de le redéclarer

    implicitWidth:  120
    implicitHeight: 30
    radius: T.Theme.radiusSm

    // Couleurs selon état
    color: {
        if (!root.enabled) return root.accent ? T.Theme.bgSurface : T.Theme.bgPanel
        if (hover.containsMouse) return root.accent ? T.Theme.accentHover : Qt.lighter(T.Theme.border, 1.3)
        return root.accent ? T.Theme.accent : T.Theme.bgSurface
    }
    border.color: root.accent ? "transparent" : T.Theme.border
    border.width: root.accent ? 0 : 1

    Behavior on color { ColorAnimation { duration: 120 } }

    Text {
        anchors.centerIn: parent
        text:  root.text
        color: root.enabled ? T.Theme.textPrimary : T.Theme.textDim
        font.family:    T.Theme.fontUi
        font.pixelSize: T.Theme.fontSizeSm
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment:   Text.AlignVCenter
    }

    MouseArea {
        id:            hover
        anchors.fill:  parent
        hoverEnabled:  true
        cursorShape:   root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked:     if (root.enabled) root.clicked()
    }
}
