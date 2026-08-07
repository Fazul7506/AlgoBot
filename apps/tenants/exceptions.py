class TenantError(Exception): pass
class TenantIsolationError(TenantError): pass
class QuotaExceeded(TenantError): pass
class BillingError(TenantError): pass
class LicenseError(TenantError): pass
