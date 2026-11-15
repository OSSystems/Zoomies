// Shown while Zoomies is copied: Zip over the same sky as the kids' screens.
import QtQuick 2.15
import calamares.slideshow 1.0

Presentation {
    id: presentation

    function onActivate() { }
    function onLeave() { }

    Slide {
        Rectangle {
            anchors.fill: parent
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#7fd3ff" }
                GradientStop { position: 0.55; color: "#b8ecff" }
                GradientStop { position: 1.0; color: "#c8f5c0" }
            }
        }
        Image {
            id: zip
            source: "zip.png"
            fillMode: Image.PreserveAspectFit
            width: parent.width * 0.35
            anchors.centerIn: parent
            anchors.verticalCenterOffset: -parent.height * 0.08
        }
        Text {
            anchors.top: zip.bottom
            anchors.topMargin: 24
            anchors.horizontalCenter: parent.horizontalCenter
            text: "Zip is getting your computer ready."
            font.family: "Andika"
            font.pixelSize: 28
            color: "#1d3557"
        }
    }
}
