using System;
using LSPD_First_Response.Mod.API;
using Rage;

namespace LSPDFRDispatch
{
    public class EntryPoint : Plugin
    {
        public override void Initialize()
        {
            Game.LogTrivial("[LSPDFRDispatch] Plugin loaded successfully!");
            Game.DisplayNotification("~b~LSPDFR Dispatch~w~ plugin loaded.");
            Functions.OnOnDutyStateChanged += OnDutyStateChanged;
        }

        public override void Finally()
        {
            Game.LogTrivial("[LSPDFRDispatch] Plugin unloaded.");
        }

        private void OnDutyStateChanged(bool onDuty)
        {
            if (onDuty)
                Game.LogTrivial("[LSPDFRDispatch] Officer on duty.");
            else
                Game.LogTrivial("[LSPDFRDispatch] Officer off duty.");
        }
    }
}
