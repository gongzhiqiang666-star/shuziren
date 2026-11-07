import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.scalar.Scalar;
import java.nio.charset.StandardCharsets;

public class DumpCythonSlots extends GhidraScript {
    public void run() throws Exception {
        var function = getFunctionAt(toAddr("180160a20"));
        var instructions = currentProgram.getListing().getInstructions(function.getBody(), true);
        while (instructions.hasNext()) {
            var instruction = instructions.next();
            if (!"ADD".equals(instruction.getMnemonicString())) continue;
            Scalar scalar = null;
            for (Object object : instruction.getOpObjects(1)) if (object instanceof Scalar) scalar = (Scalar)object;
            if (scalar == null) continue;
            long slot = scalar.getUnsignedValue();
            String wanted = String.format("0x%x", slot);
            boolean match = false;
            for (String argument : getScriptArgs()) if (Long.decode(argument) == slot) match = true;
            if (!match) continue;
            println(wanted + "\tmatched " + instruction.getAddress());
            var cursor = instruction;
            Address raw = null;
            long length = -1;
            for (int step = 0; step < 8 && cursor != null; step++, cursor = cursor.getNext()) {
                if (raw == null && "LEA".equals(cursor.getMnemonicString())) {
                    for (Object object : cursor.getOpObjects(1)) if (object instanceof Address) raw = (Address)object;
                    if (raw == null) raw = cursor.getAddress(1);
                } else if (raw != null && "MOV".equals(cursor.getMnemonicString())) {
                    for (Object object : cursor.getOpObjects(1)) if (object instanceof Scalar) length = ((Scalar)object).getUnsignedValue();
                    if (length >= 0) break;
                }
            }
            if (raw == null || length < 0 || length > 10000) continue;
            byte[] bytes = new byte[(int)length];
            currentProgram.getMemory().getBytes(raw, bytes);
            println(wanted + "\t" + new String(bytes, StandardCharsets.UTF_8).replace("\n", "\\n"));
        }
    }
}
