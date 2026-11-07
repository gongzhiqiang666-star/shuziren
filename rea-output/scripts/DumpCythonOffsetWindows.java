import ghidra.app.script.GhidraScript;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpCythonOffsetWindows extends GhidraScript {
    public void run() throws Exception {
        var function = getFunctionAt(toAddr(getScriptArgs()[0]));
        StringBuilder out = new StringBuilder();
        for (int arg = 2; arg < getScriptArgs().length; arg++) {
            String needle = "[RCX + 0x" + getScriptArgs()[arg] + "]";
            var instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
            while (instructions.hasNext()) {
                var match = instructions.next();
                if (!match.toString().contains(needle)) continue;
                var line = match;
                for (int i = 0; i < 5 && line.getPrevious() != null; i++) line = line.getPrevious();
                out.append("=== 0x").append(getScriptArgs()[arg]).append(" ===\n");
                for (int i = 0; i < 12 && line != null; i++, line = line.getNext())
                    out.append(line.getAddress()).append('\t').append(line).append('\n');
                break;
            }
        }
        Files.writeString(Path.of(getScriptArgs()[1]), out.toString());
    }
}
