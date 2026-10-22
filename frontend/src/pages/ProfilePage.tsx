import { useEffect, useState, type FormEvent, type KeyboardEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { toast } from "sonner";
import { api, ApiError, type Profile } from "@/lib/api";
import { useAuth } from "@/contexts/AuthContext";
import { addEntry, MAX_ITEM_CHARS } from "@/lib/profile";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

interface ChipsProps {
  id: string;
  label: string;
  hint: string;
  placeholder: string;
  entries: string[];
  onChange: (entries: string[]) => void;
}

/** A list of short phrases: type one and press Enter (or Add); click the x on a chip to remove it. */
function Chips({ id, label, hint, placeholder, entries, onChange }: ChipsProps) {
  const [draft, setDraft] = useState("");

  const commit = () => {
    onChange(addEntry(entries, draft));
    setDraft("");
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (event.key === "Enter") {
      event.preventDefault(); // Enter adds the entry; it does not submit the whole form
      commit();
    }
  };

  return (
    <div className="space-y-2">
      <Label htmlFor={id}>{label}</Label>
      <p className="text-xs text-muted-foreground">{hint}</p>
      <div className="flex gap-2">
        <Input
          id={id}
          value={draft}
          maxLength={MAX_ITEM_CHARS}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
        />
        <Button type="button" variant="secondary" onClick={commit} disabled={!draft.trim()}>
          Add
        </Button>
      </div>
      {entries.length > 0 && (
        <ul className="flex flex-wrap gap-2" aria-label={`${label} added`}>
          {entries.map((entry) => (
            <li key={entry} className="flex items-center gap-1 rounded-full bg-accent py-1 pl-3 pr-1 text-sm text-accent-foreground">
              {entry}
              <button
                type="button"
                aria-label={`Remove ${entry}`}
                onClick={() => onChange(entries.filter((e) => e !== entry))}
                className="flex h-5 w-5 items-center justify-center rounded-full hover:bg-background/40"
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ProfileField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <h2 className="text-sm font-medium text-muted-foreground">{label}</h2>
      <div className="text-foreground">{children ?? <span className="text-sm text-muted-foreground">Not added</span>}</div>
    </div>
  );
}

function ReadOnlyChips({ entries }: { entries: string[] }) {
  return (
    <ul className="flex flex-wrap gap-2">
      {entries.map((entry) => (
        <li key={entry} className="rounded-full bg-accent px-3 py-1 text-sm text-accent-foreground">
          {entry}
        </li>
      ))}
    </ul>
  );
}

const EMPTY: Profile = { age: null, preferences: [], medical_conditions: [] };

/** The shopper's own details: age, preferences and medical conditions. Private to the logged-in shopper. */
export default function ProfilePage() {
  const { logout } = useAuth();
  const queryClient = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["profile"],
    queryFn: api.getProfile,
    retry: false, // a failed load shows "Try again"; automatic retries would only delay that
  });
  const [form, setForm] = useState<Profile>(EMPTY);
  const [ageText, setAgeText] = useState("");
  const [editing, setEditing] = useState(false);

  useEffect(() => {
    if (error instanceof ApiError && error.status === 401) logout();
  }, [error, logout]);

  // Fill the form once the saved profile arrives (and again after a save, which returns the stored copy).
  useEffect(() => {
    if (!data) return;
    setForm(data);
    setAgeText(data.age === null ? "" : String(data.age));
  }, [data]);

  const save = useMutation({
    mutationFn: api.saveProfile,
    onSuccess: (saved) => {
      queryClient.setQueryData(["profile"], saved);
      setEditing(false);
      toast.success("Profile saved");
    },
    onError: (err) => {
      if (err instanceof ApiError && err.status === 401) logout();
      else toast.error(err instanceof ApiError ? err.message : "Couldn’t save your profile");
    },
  });

  const ageNumber = ageText.trim() === "" ? null : Number(ageText);
  const ageInvalid = ageNumber !== null && (!Number.isInteger(ageNumber) || ageNumber < 0 || ageNumber > 120);
  const candidate: Profile = { ...form, age: ageInvalid ? form.age : ageNumber };
  const unchanged = JSON.stringify(candidate) === JSON.stringify(data ?? EMPTY);

  const cancel = () => {
    setForm(data ?? EMPTY); // throw away what was typed
    setAgeText(data?.age == null ? "" : String(data.age));
    setEditing(false);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!ageInvalid) save.mutate(candidate);
  };

  return (
    <div className="mx-auto max-w-2xl p-6 lg:p-8">
      <h1 className="mb-1 text-3xl font-bold text-foreground">Profile</h1>
      <p className="mb-8 text-muted-foreground">
        What you tell us here is private to your account. Add as much or as little as you like.
      </p>

      {isLoading ? (
        <div className="space-y-4" aria-busy="true">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-20 animate-pulse rounded-xl bg-card" />
          ))}
        </div>
      ) : error ? (
        <div role="alert" className="flex flex-col items-center gap-3 py-16 text-center text-muted-foreground">
          <p>We couldn’t load your profile.</p>
          <Button variant="outline" onClick={() => refetch()}>
            Try again
          </Button>
        </div>
      ) : !editing ? (
        <section aria-label="Your profile" className="space-y-6 rounded-xl border border-border bg-card p-6">
          <ProfileField label="Age">{data?.age == null ? null : `${data.age} years`}</ProfileField>
          <ProfileField label="Preferences">{data?.preferences.length ? <ReadOnlyChips entries={data.preferences} /> : null}</ProfileField>
          <ProfileField label="Medical conditions">
            {data?.medical_conditions.length ? <ReadOnlyChips entries={data.medical_conditions} /> : null}
          </ProfileField>
          <Button type="button" onClick={() => setEditing(true)}>
            Edit
          </Button>
        </section>
      ) : (
        <form onSubmit={onSubmit} className="space-y-8 rounded-xl border border-border bg-card p-6">
          <div className="space-y-2">
            <Label htmlFor="age">Age</Label>
            <Input
              id="age"
              inputMode="numeric"
              className="max-w-[8rem]"
              placeholder="e.g. 34"
              value={ageText}
              aria-invalid={ageInvalid}
              onChange={(e) => setAgeText(e.target.value)}
            />
            {ageInvalid && (
              <p role="alert" className="text-xs text-destructive">
                Enter a whole number from 0 to 120.
              </p>
            )}
          </div>

          <Chips
            id="preferences"
            label="Preferences"
            hint="Foods, brands or habits, such as vegetarian, only Amul, low salt."
            placeholder="Add a preference"
            entries={form.preferences}
            onChange={(preferences) => setForm((f) => ({ ...f, preferences }))}
          />

          <Chips
            id="medical"
            label="Medical conditions"
            hint="Allergies or conditions that affect what you buy, such as peanut allergy, diabetes."
            placeholder="Add a medical condition"
            entries={form.medical_conditions}
            onChange={(medical_conditions) => setForm((f) => ({ ...f, medical_conditions }))}
          />

          <div className="flex gap-2">
            <Button type="submit" disabled={save.isPending || unchanged || ageInvalid}>
              {save.isPending ? "Saving…" : "Save profile"}
            </Button>
            <Button type="button" variant="outline" onClick={cancel} disabled={save.isPending}>
              Cancel
            </Button>
          </div>
        </form>
      )}
    </div>
  );
}
