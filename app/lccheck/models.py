from django.db import models


class OfficerDecision(models.Model):
    DECISION_CHOICES = [
        ("ACCEPT", "Accept (Waived / OK)"),
        ("REFER", "Refer (Needs More Info / Escalate)"),
        ("REJECT", "Reject (Refuse / Discrepancy Upheld)"),
    ]

    lc_number = models.CharField(max_length=64, db_index=True)
    invoice_number = models.CharField(max_length=64, blank=True, default="", db_index=True)
    field = models.CharField(max_length=64)
    decision = models.CharField(max_length=20, choices=DECISION_CHOICES, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    ai_explanation = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lc_number", "invoice_number", "field"],
                name="unique_officer_decision_per_field",
            )
        ]

    def __str__(self):
        return f"{self.lc_number} - {self.invoice_number or 'NO_INV'} - {self.field}: {self.decision}"
