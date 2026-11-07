import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.scalar.Scalar;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpCythonStringTableAt extends GhidraScript {
    public void run() throws Exception {
        String initAddress = getScriptArgs()[0];
        String outputPath = getScriptArgs()[1];
        StringBuilder out = new StringBuilder();
        var iterator = currentProgram.getListing().getDefinedData(true);
        while (iterator.hasNext()) {
            var data = iterator.next();
            String value;
            try { value = StringDataInstance.getStringDataInstance(data).getStringValue(); }
            catch (Exception error) { continue; }
            if (value == null) continue;
            for (var ref : getReferencesTo(data.getAddress())) {
                var function = getFunctionContaining(ref.getFromAddress());
                if (function == null || !function.getEntryPoint().equals(toAddr(initAddress))) continue;
                var instruction = currentProgram.getListing().getInstructionContaining(ref.getFromAddress());
                for (int i = 0; i < 10 && instruction != null; i++, instruction = instruction.getPrevious()) {
                    String rendered = instruction.toString();
                    int marker = rendered.indexOf("[RCX + 0x");
                    if (marker < 0) continue;
                    int end = rendered.indexOf(']', marker);
                    if (end < 0) continue;
                    String hex = rendered.substring(marker + 9, end);
                    long offset = Long.parseUnsignedLong(hex, 16);
                    out.append(String.format("0x%x\t%s\n", offset, value.replace("\n", "\\n")));
                    break;
                }
            }
        }
        Files.writeString(Path.of(outputPath), out.toString());
    }
}
