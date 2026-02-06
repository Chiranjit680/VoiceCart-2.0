import { Mic, Square } from "lucide-react";
import { cn } from "@/lib/utils";

interface RecordButtonProps {
  isRecording: boolean;
  disabled?: boolean;
  onClick: () => void;
}

export function RecordButton({ isRecording, disabled, onClick }: RecordButtonProps) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "relative flex h-24 w-24 items-center justify-center rounded-full transition-all duration-300 focus:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        isRecording
          ? "bg-destructive text-destructive-foreground scale-110"
          : "bg-primary text-primary-foreground hover:scale-105 hover:shadow-[0_0_30px_hsl(var(--primary)/0.4)]",
        disabled && "opacity-40 cursor-not-allowed"
      )}
    >
      {/* Pulse rings when recording */}
      {isRecording && (
        <>
          <span className="absolute inset-0 animate-ping rounded-full bg-destructive/30" />
          <span className="absolute inset-[-8px] animate-pulse rounded-full border-2 border-destructive/40" />
        </>
      )}

      {isRecording ? (
        <Square className="h-8 w-8 relative z-10" />
      ) : (
        <Mic className="h-10 w-10 relative z-10" />
      )}
    </button>
  );
}
