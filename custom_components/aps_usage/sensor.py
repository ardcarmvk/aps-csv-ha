"""Sensor platform for APS Usage — kWh and billing sensors."""

from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import APSDataCoordinator
from .api import APSSolarData, APSUsageData
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up APS Usage sensors."""
    coordinator: APSDataCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [
        APSYesterdayKwhSensor(coordinator, entry),
        APSCurrentCycleKwhSensor(coordinator, entry),
        APSThirtyDayKwhSensor(coordinator, entry),
        APSOnPeakYesterdaySensor(coordinator, entry),
        APSOffPeakYesterdaySensor(coordinator, entry),
        APSBalanceSensor(coordinator, entry),
        APSDueDateSensor(coordinator, entry),
        APSBillPeriodEndSensor(coordinator, entry),
        APSLastPaymentSensor(coordinator, entry),
    ]
    if coordinator.api.is_solar:
        entities += [
            APSGridImportYesterdaySensor(coordinator, entry),
            APSGridExportYesterdaySensor(coordinator, entry),
            APSSolarGeneratedYesterdaySensor(coordinator, entry),
            APSSolarSelfUsedYesterdaySensor(coordinator, entry),
            APSCycleGridImportSensor(coordinator, entry),
            APSCycleGridExportSensor(coordinator, entry),
            APSCycleSolarGeneratedSensor(coordinator, entry),
            APSPeakDemandSensor(coordinator, entry),
        ]
    async_add_entities(entities, update_before_add=True)


class _APSBase(CoordinatorEntity, SensorEntity):
    """Base class for APS sensors."""

    def __init__(
        self, coordinator: APSDataCoordinator, entry: ConfigEntry, key: str
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"

    @property
    def _usage(self) -> APSUsageData | None:
        if self.coordinator.data:
            return self.coordinator.data.get("usage")
        return None

    @property
    def _financial(self) -> dict:
        if self.coordinator.data:
            return self.coordinator.data.get("financial", {})
        return {}

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fin = self._financial
        usage = self._usage
        attrs: dict[str, Any] = {
            "account_id": fin.get("account_id", ""),
            "premise_address": fin.get("premise_address", ""),
        }
        if usage:
            attrs["latest_data_date"] = usage.latest_date
            attrs["bill_cycle_start"] = usage.current_bill_cycle_start
        return attrs


class APSYesterdayKwhSensor(_APSBase):
    """Yesterday's total energy usage in kWh."""

    _attr_name = "APS Yesterday kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Snapshot that goes up and down; HA forbids 'measurement' with the energy device class.
    _attr_state_class = None
    _attr_icon = "mdi:lightning-bolt"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "yesterday_kwh")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        return usage.yesterday_kwh if usage else None


class APSCurrentCycleKwhSensor(_APSBase):
    """Total energy usage since the current billing cycle started."""

    _attr_name = "APS Current Billing Cycle kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_icon = "mdi:home-lightning-bolt"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_cycle_kwh")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        return usage.current_cycle_kwh if usage else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        attrs["rate_plan"] = self._financial.get("rate_plan")
        return attrs


class APSThirtyDayKwhSensor(_APSBase):
    """Total energy usage over the last 30 days."""

    _attr_name = "APS 30-Day kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Snapshot that goes up and down; HA forbids 'measurement' with the energy device class.
    _attr_state_class = None
    _attr_icon = "mdi:calendar-month"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "thirty_day_kwh")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        return usage.period_kwh(30) if usage else None


class APSOnPeakYesterdaySensor(_APSBase):
    """Yesterday's on-peak energy usage."""

    _attr_name = "APS Yesterday On-Peak kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Snapshot that goes up and down; HA forbids 'measurement' with the energy device class.
    _attr_state_class = None
    _attr_icon = "mdi:lightning-bolt-circle"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "on_peak_yesterday")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        return usage.on_peak_kwh_yesterday if usage else None


class APSOffPeakYesterdaySensor(_APSBase):
    """Yesterday's off-peak energy usage."""

    _attr_name = "APS Yesterday Off-Peak kWh"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Snapshot that goes up and down; HA forbids 'measurement' with the energy device class.
    _attr_state_class = None
    _attr_icon = "mdi:lightning-bolt-outline"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "off_peak_yesterday")

    @property
    def native_value(self) -> float | None:
        usage = self._usage
        return usage.off_peak_kwh_yesterday if usage else None


class _APSSolarBase(_APSBase):
    """Base class for solar sensors (only created on solar accounts)."""

    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    # Snapshot that goes up and down; HA forbids 'measurement' with the energy device class.
    _attr_state_class = None
    _attr_suggested_display_precision = 2

    @property
    def _solar(self) -> APSSolarData | None:
        if self.coordinator.data:
            return self.coordinator.data.get("solar")
        return None

    @property
    def available(self) -> bool:
        # The solar endpoint is best-effort; go unavailable when it fails
        return super().available and self._solar is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        solar = self._solar
        if solar:
            attrs["latest_data_date"] = solar.latest_date
        return attrs


class APSGridImportYesterdaySensor(_APSSolarBase):
    """kWh drawn from the grid on the latest complete day."""

    _attr_name = "APS Yesterday Grid Import kWh"
    _attr_icon = "mdi:transmission-tower-import"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "grid_import_yesterday")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.grid_import_yesterday if solar else None


class APSGridExportYesterdaySensor(_APSSolarBase):
    """Solar kWh sold back to the grid on the latest complete day."""

    _attr_name = "APS Yesterday Grid Export kWh"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "grid_export_yesterday")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.exported_yesterday if solar else None


class APSSolarGeneratedYesterdaySensor(_APSSolarBase):
    """Total solar kWh produced on the latest complete day."""

    _attr_name = "APS Yesterday Solar Generated kWh"
    _attr_icon = "mdi:solar-power"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "solar_generated_yesterday")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.generated_yesterday if solar else None


class APSSolarSelfUsedYesterdaySensor(_APSSolarBase):
    """Solar kWh consumed on-site on the latest complete day."""

    _attr_name = "APS Yesterday Solar Self-Consumed kWh"
    _attr_icon = "mdi:home-lightning-bolt-outline"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "solar_self_used_yesterday")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.self_used_yesterday if solar else None


class _APSSolarCycleBase(_APSSolarBase):
    """Cumulative-within-billing-cycle solar sensor (Energy Dashboard).

    TOTAL_INCREASING resets at each billing cycle boundary; HA's statistics
    treat the drop as a meter reset, so long-term totals stay correct.
    """

    _attr_state_class = SensorStateClass.TOTAL_INCREASING

    def _cycle_start(self) -> str | None:
        usage = self._usage
        return usage.current_bill_cycle_start if usage else None


class APSCycleGridImportSensor(_APSSolarCycleBase):
    """Grid import kWh since the billing cycle started."""

    _attr_name = "APS Current Cycle Grid Import kWh"
    _attr_icon = "mdi:transmission-tower-import"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "cycle_grid_import")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.grid_import_since(self._cycle_start()) if solar else None


class APSCycleGridExportSensor(_APSSolarCycleBase):
    """Grid export kWh since the billing cycle started."""

    _attr_name = "APS Current Cycle Grid Export kWh"
    _attr_icon = "mdi:transmission-tower-export"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "cycle_grid_export")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.exported_since(self._cycle_start()) if solar else None


class APSCycleSolarGeneratedSensor(_APSSolarCycleBase):
    """Solar production kWh since the billing cycle started."""

    _attr_name = "APS Current Cycle Solar Generated kWh"
    _attr_icon = "mdi:solar-power-variant"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "cycle_solar_generated")

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        return solar.generated_since(self._cycle_start()) if solar else None


def _parse_day(val: Any) -> date | None:
    try:
        return datetime.strptime(str(val)[:10], "%Y-%m-%d").date()  # noqa: DTZ007
    except (ValueError, TypeError):
        return None


def _billed_kw(kw: float | None) -> float | None:
    """APS bills demand in tenths of a kW, rounded down.

    Confirmed on two R-3 bills: PeakDemand 0.31 → 0.3 kW and 0.37 → 0.3 kW.
    """
    if kw is None:
        return None
    return math.floor(kw * 10 + 1e-9) / 10


class APSBillPeriodEndSensor(_APSBase):
    """Last day of the most recently billed period (billSegmentEndDate).

    The current, unbilled period starts the day after. More reliable than
    bill_cycle_start, and unlike the due date it is the actual boundary.
    """

    _attr_name = "APS Bill Period End"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-end"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "bill_period_end")

    @property
    def native_value(self) -> date | None:  # type: ignore[override]
        return _parse_day(self._financial.get("bill_period_end"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fin = self._financial
        end = self.native_value
        days = fin.get("bill_period_days")
        try:
            start = end - timedelta(days=int(days) - 1) if end and days else None
        except (ValueError, TypeError):
            start = None
        return {
            "current_period_start": (end + timedelta(days=1)).isoformat() if end else None,
            "billed_period_start": start.isoformat() if start else None,
            "billed_period_days": days,
            "bill_date": fin.get("bill_date"),
        }


class APSPeakDemandSensor(_APSSolarBase):
    """Highest on-peak demand (kW) so far in the current billing period.

    From APS's own per-day PeakDemand, so it lags about a day. The period
    starts the day after billSegmentEndDate; if that is missing it falls
    back to bill_cycle_start (see the `period_source` attribute).
    """

    _attr_name = "APS Billing Period Peak Demand"
    _attr_native_unit_of_measurement = UnitOfPower.KILO_WATT
    _attr_device_class = SensorDeviceClass.POWER
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:podium-gold"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "period_peak_demand")

    def _period(self) -> tuple[str | None, str]:
        end = _parse_day(self._financial.get("bill_period_end"))
        if end:
            return (end + timedelta(days=1)).isoformat(), "bill_period_end"
        usage = self._usage
        return (usage.current_bill_cycle_start if usage else None), "bill_cycle_start"

    @property
    def native_value(self) -> float | None:
        solar = self._solar
        if not solar:
            return None
        kw, _ = solar.peak_demand(self._period()[0])
        return kw

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        attrs = super().extra_state_attributes
        solar = self._solar
        start, source = self._period()
        attrs.update({"period_start": start, "period_source": source})
        if not solar:
            return attrs
        kw, day = solar.peak_demand(start)
        attrs.update(
            {
                "peak_date": day,
                "billed_kw": _billed_kw(kw),
                "daily": solar.daily_peak_demand(start),
            }
        )
        # The billed period, to check against the bill's demand line.
        fin = self._financial
        end = _parse_day(fin.get("bill_period_end"))
        try:
            days = int(fin.get("bill_period_days") or 0)
        except (ValueError, TypeError):
            days = 0
        if end and days:
            prev_kw, prev_day = solar.peak_demand(
                (end - timedelta(days=days - 1)).isoformat(), end.isoformat()
            )
            attrs.update(
                {
                    "previous_period_peak_kw": prev_kw,
                    "previous_period_peak_date": prev_day,
                    "previous_period_billed_kw": _billed_kw(prev_kw),
                }
            )
        return attrs


class APSBalanceSensor(_APSBase):
    """Current outstanding bill balance."""

    _attr_name = "APS Current Balance"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:currency-usd"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "balance")

    @property
    def native_value(self) -> float | None:
        val = self._financial.get("outstanding_balance")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        fin = self._financial
        return {
            "account_id": fin.get("account_id", ""),
            "due_date": fin.get("due_date", ""),
            "new_charges": fin.get("new_charges"),
            "auto_pay": fin.get("auto_pay"),
            "budget_billing": fin.get("budget_billing"),
            "last_payment_amount": fin.get("last_payment_amount"),
            "last_payment_date": fin.get("last_payment_date"),
        }


class APSDueDateSensor(_APSBase):
    """Bill due date."""

    _attr_name = "APS Bill Due Date"
    _attr_device_class = SensorDeviceClass.DATE
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "due_date")

    @property
    def native_value(self):  # type: ignore[override]
        """Return due date as a date object."""
        val = self._financial.get("due_date", "")
        if not val:
            return None
        for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y", "%m-%d-%y"):
            try:
                return datetime.strptime(val, fmt).date()  # noqa: DTZ007
            except ValueError:
                continue
        return None


class APSLastPaymentSensor(_APSBase):
    """Most recent payment amount."""

    _attr_name = "APS Last Payment"
    _attr_native_unit_of_measurement = "USD"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = None
    _attr_icon = "mdi:check-circle"
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: APSDataCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "last_payment")

    @property
    def native_value(self) -> float | None:
        val = self._financial.get("last_payment_amount")
        try:
            return float(val) if val is not None else None
        except (ValueError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "last_payment_date": self._financial.get("last_payment_date"),
            "account_id": self._financial.get("account_id", ""),
        }
