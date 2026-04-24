"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { TERMS_URL, PRIVACY_URL } from "@/lib/constants";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";

export function TermsAcceptanceModal() {
  const { requiresTermsAcceptance, acceptTerms } = useAuth();
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");

  if (!requiresTermsAcceptance) return null;

  const onAccept = async () => {
    if (!checked || submitting) return;
    setError("");
    setSubmitting(true);
    try {
      await acceptTerms();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Greška pri spremanju");
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={true} onOpenChange={() => {}}>
      <DialogContent showCloseButton={false}>
        <DialogHeader>
          <DialogTitle>Uvjeti korištenja i Pravila privatnosti</DialogTitle>
          <DialogDescription>
            Ažurirali smo naše Uvjete korištenja i Pravila privatnosti. Prije nastavka rada molimo Vas
            da ih pročitate i prihvatite.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-start gap-2">
            <Checkbox
              id="terms_modal_accept"
              checked={checked}
              onCheckedChange={(v) => setChecked(v)}
              disabled={submitting}
              className="mt-0.5"
            />
            <Label
              htmlFor="terms_modal_accept"
              className="text-sm leading-relaxed font-normal cursor-pointer"
            >
              Prihvaćam{" "}
              <a
                href={TERMS_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-4 hover:text-primary/80"
              >
                Uvjete korištenja
              </a>{" "}
              i{" "}
              <a
                href={PRIVACY_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary underline underline-offset-4 hover:text-primary/80"
              >
                Pravila privatnosti
              </a>
              .
            </Label>
          </div>

          {error && (
            <div className="rounded-lg bg-destructive/10 px-3 py-2 text-sm text-destructive">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button onClick={onAccept} disabled={!checked || submitting}>
            {submitting ? "Spremanje..." : "Prihvaćam i nastavi"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
