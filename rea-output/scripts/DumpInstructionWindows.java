import ghidra.app.script.GhidraScript;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpInstructionWindows extends GhidraScript {
    public void run() throws Exception {
        StringBuilder out = new StringBuilder();
        for (int i = 1; i < getScriptArgs().length; i++) {
            var address = toAddr(getScriptArgs()[i]);
            var instruction = currentProgram.getListing().getInstructionContaining(address);
            if (instruction == null) continue;
            for (int before = 0; before < 8 && instruction.getPrevious() != null; before++) {
                instruction = instruction.getPrevious();
            }
            out.append("=== ").append(address).append(" ===\n");
            for (int line = 0; line < 18 && instruction != null; line++) {
                out.append(instruction.getAddress()).append("\t").append(instruction).append("\n");
                instruction = instruction.getNext();
            }
        }
        Files.writeString(Path.of(getScriptArgs()[0]), out.toString());
    }
}
