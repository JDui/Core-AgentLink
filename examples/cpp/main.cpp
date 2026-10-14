// C++ host integration through structured CLI arguments; never concatenate shell text.
#include <QCoreApplication>
#include <QFileInfo>
#include <QJsonDocument>
#include <QJsonObject>
#include <QProcess>
#include <QTextStream>

int main(int argc, char *argv[]) {
    QCoreApplication application(argc, argv);
    const auto args = application.arguments();
    if (args.size() != 4) {
        QTextStream(stderr) << "Usage: cal_qt_client <absolute-cal-executable> <state-dir> <session-id>\n";
        return 2;
    }
    if (!QFileInfo(args.at(1)).isAbsolute() || !QFileInfo(args.at(1)).isFile()) {
        QTextStream(stderr) << "An absolute CLI executable path is required\n";
        return 2;
    }
    QProcess process;
    process.setProgram(args.at(1));
    process.setArguments({"inspect", "--state-dir", args.at(2), "--project-id", "demo",
                          "--session", args.at(3), "--timeout", "5"});
    process.start();
    if (!process.waitForStarted(3000) || !process.waitForFinished(8000)) {
        process.kill();
        process.waitForFinished(2000);
        QTextStream(stderr) << "CLI unavailable or timed out; inspect before retrying any mutation\n";
        return 1;
    }
    const auto output = process.readAllStandardOutput();
    QJsonParseError error;
    const auto packet = QJsonDocument::fromJson(output, &error);
    if (output.size() > 65536 || error.error != QJsonParseError::NoError || !packet.isObject()
        || process.exitStatus() != QProcess::NormalExit || process.exitCode() != 0
        || packet.object().value("version").toInt(-1) != 1
        || !packet.object().value("ok").isBool()
        || !packet.object().value("ok").toBool()) {
        QTextStream(stderr) << "CLI returned an error or invalid JSON\n";
        return 1;
    }
    QTextStream(stdout) << QString::fromUtf8(packet.toJson(QJsonDocument::Indented));
    return 0;
}

