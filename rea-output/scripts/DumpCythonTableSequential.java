import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.StringDataInstance;
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;

public class DumpCythonTableSequential extends GhidraScript {
    public void run() throws Exception {
        var function = getFunctionAt(toAddr(getScriptArgs()[0]));
        StringBuilder out = new StringBuilder();
        var instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            var instruction = instructions.next();
            String rendered = instruction.toString();
            int marker = rendered.indexOf("[RCX + 0x");
            if (marker < 0) continue;
            int end = rendered.indexOf(']', marker);
            if (end < 0) continue;
            String offset = rendered.substring(marker + 9, end);
            var candidate = instruction.getPrevious();
            String value = null;
            for (int i = 0; i < 5 && candidate != null; i++, candidate = candidate.getPrevious()) {
                String candidateText = candidate.toString();
                if (!candidateText.startsWith("LEA ") || !candidateText.contains(",[0x")) continue;
                for (int operand = 0; operand < candidate.getNumOperands(); operand++) {
                    for (Object object : candidate.getOpObjects(operand)) {
                        if (!(object instanceof Address)) continue;
                        Address address = (Address)object;
                        var data = currentProgram.getListing().getDataAt(address);
                        if (data != null) {
                            try { value = StringDataInstance.getStringDataInstance(data).getStringValue(); }
                            catch (Exception ignored) { }
                        }
                        if (value == null && currentProgram.getMemory().contains(address)) {
                            ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                            for (int index = 0; index < 512; index++) {
                                byte next = currentProgram.getMemory().getByte(address.add(index));
                                if (next == 0) break;
                                bytes.write(next);
                            }
                            if (bytes.size() > 0) value = bytes.toString(StandardCharsets.UTF_8);
                        }
                    }
                }
                if (value != null) break;
            }
            if (value == null) {
                candidate = instruction.getNext();
                for (int i = 0; i < 5 && candidate != null; i++, candidate = candidate.getNext()) {
                    String candidateText = candidate.toString();
                    if (!candidateText.startsWith("LEA ") || !candidateText.contains(",[0x")) continue;
                    for (Object object : candidate.getOpObjects(1)) {
                        if (!(object instanceof Address)) continue;
                        Address address = (Address)object;
                        if (!currentProgram.getMemory().contains(address)) continue;
                        ByteArrayOutputStream bytes = new ByteArrayOutputStream();
                        for (int index = 0; index < 512; index++) {
                            byte next = currentProgram.getMemory().getByte(address.add(index));
                            if (next == 0) break;
                            bytes.write(next);
                        }
                        if (bytes.size() > 0) value = bytes.toString(StandardCharsets.UTF_8);
                    }
                    if (value != null) break;
                }
            }
            out.append("0x").append(offset).append('\t')
               .append(value == null ? "?" : value.replace("\n", "\\n")).append('\n');
        }
        Files.writeString(Path.of(getScriptArgs()[1]), out.toString());
    }
}
