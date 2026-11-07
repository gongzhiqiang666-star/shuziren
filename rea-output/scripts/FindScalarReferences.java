import ghidra.app.script.GhidraScript;
import ghidra.program.model.scalar.Scalar;

public class FindScalarReferences extends GhidraScript {
    public void run() throws Exception {
        long wanted = Long.decode(getScriptArgs()[0]);
        var instructions = currentProgram.getListing().getInstructions(true);
        while (instructions.hasNext()) {
            var instruction = instructions.next();
            boolean match = false;
            for (int operand = 0; operand < instruction.getNumOperands(); operand++) {
                for (Object object : instruction.getOpObjects(operand)) {
                    if (object instanceof Scalar && ((Scalar)object).getUnsignedValue() == wanted) match = true;
                }
            }
            if (match) println(instruction.getAddress() + "\t" + instruction);
        }
    }
}
