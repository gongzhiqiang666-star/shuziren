import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.StringDataInstance;
import ghidra.program.model.scalar.Scalar;
import java.nio.file.Files;
import java.nio.file.Path;

public class DumpCythonStringTable extends GhidraScript {
    public void run() throws Exception {
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
                if (function == null || !function.getEntryPoint().equals(toAddr("180160a20"))) continue;
                var instruction = currentProgram.getListing().getInstructionContaining(ref.getFromAddress());
                for (int i = 0; i < 8 && instruction != null; i++, instruction = instruction.getPrevious()) {
                    if (!"ADD".equals(instruction.getMnemonicString())) continue;
                    for (Object object : instruction.getOpObjects(1)) {
                        if (object instanceof Scalar) {
                            long offset = ((Scalar)object).getUnsignedValue();
                            out.append(String.format("0x%x\t%s\n", offset, value.replace("\n", "\\n")));
                        }
                    }
                    break;
                }
            }
        }
        Files.writeString(Path.of(getScriptArgs()[0]), out.toString());
    }
}
