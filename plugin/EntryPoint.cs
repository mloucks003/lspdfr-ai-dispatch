using Rage;

namespace LSPDFRDispatch
{
    public class EntryPoint : Plugin
    {
        public override void Initialize()
        {
            Game.LogTrivial("[LSPDFRDispatch] Plugin loaded!");
            Game.DisplayNotification("~b~LSPDFR Dispatch~w~ loaded.");
        }

        public override void Finally()
        {
            Game.LogTrivial("[LSPDFRDispatch] Plugin unloaded.");
        }
    }
}
