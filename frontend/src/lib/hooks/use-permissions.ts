import { useAuth } from "@/lib/auth"

type Role = "admin" | "doctor" | "nurse" | "receptionist"

export interface Permissions {
  // Page visibility
  canViewSettings: boolean
  canViewMedicalRecords: boolean
  canViewCezih: boolean
  canViewDocuments: boolean

  // Clinical data access
  canViewClinicalData: boolean
  canCreateMedicalRecord: boolean
  canEditMedicalRecord: boolean

  // Patient management
  canDeletePatient: boolean

  // Procedures
  canCreateProcedure: boolean
  canEditProcedure: boolean
  canDeleteProcedure: boolean

  // Documents
  canUploadDocuments: boolean

  // CEZIH operations (requires formal authorization + personal credential)
  canPerformCezihOps: boolean

  // HZZO contract features (e-Recept, e-Uputnica)
  canUseHzzo: boolean

  // Access control
  canSetRecordSensitivity: boolean
}

const ROLE_PERMISSIONS: Record<Role, Permissions> = {
  admin: {
    canViewSettings: true,
    canViewMedicalRecords: true,
    canViewCezih: true,
    canViewDocuments: true,
    canViewClinicalData: true,
    canCreateMedicalRecord: true,
    canEditMedicalRecord: true,
    canDeletePatient: true,
    canCreateProcedure: true,
    canEditProcedure: true,
    canDeleteProcedure: true,
    canUploadDocuments: true,
    canPerformCezihOps: true,
    canUseHzzo: false,
    canSetRecordSensitivity: true,
  },
  doctor: {
    canViewSettings: false,
    canViewMedicalRecords: true,
    canViewCezih: true,
    canViewDocuments: true,
    canViewClinicalData: true,
    canCreateMedicalRecord: true,
    canEditMedicalRecord: true,
    canDeletePatient: false,
    canCreateProcedure: true,
    canEditProcedure: true,
    canDeleteProcedure: true,
    canUploadDocuments: true,
    canPerformCezihOps: true,
    canUseHzzo: false,
    canSetRecordSensitivity: true,
  },
  nurse: {
    canViewSettings: false,
    canViewMedicalRecords: true,
    canViewCezih: false,
    canViewDocuments: true,
    canViewClinicalData: true,
    canCreateMedicalRecord: false,
    canEditMedicalRecord: false,
    canDeletePatient: false,
    canCreateProcedure: true,
    canEditProcedure: true,
    canDeleteProcedure: false,
    canUploadDocuments: true,
    canPerformCezihOps: false,
    canUseHzzo: false,
    canSetRecordSensitivity: false,
  },
  receptionist: {
    canViewSettings: false,
    canViewMedicalRecords: false,
    canViewCezih: false,
    canViewDocuments: false,
    canViewClinicalData: false,
    canCreateMedicalRecord: false,
    canEditMedicalRecord: false,
    canDeletePatient: false,
    canCreateProcedure: false,
    canEditProcedure: false,
    canDeleteProcedure: false,
    canUploadDocuments: false,
    canPerformCezihOps: false,
    canUseHzzo: false,
    canSetRecordSensitivity: false,
  },
}

export function usePermissions(): Permissions {
  const { user } = useAuth()
  const role = (user?.role as Role) ?? "receptionist"
  const base = ROLE_PERMISSIONS[role] ?? ROLE_PERMISSIONS.receptionist

  const hasHzzoContract = user?.tenant?.has_hzzo_contract ?? false

  // Admin gets CEZIH + clinical access if card is bound (formal authorization proxy)
  if (role === "admin" && user?.card_certificate_oib) {
    return {
      ...base,
      canViewMedicalRecords: true,
      canViewCezih: true,
      canViewClinicalData: true,
      canPerformCezihOps: true,
      canUseHzzo: hasHzzoContract,
      canSetRecordSensitivity: true,
    }
  }

  // Doctors/nurses with CEZIH ops: also check HZZO contract
  if (base.canPerformCezihOps) {
    return {
      ...base,
      canUseHzzo: hasHzzoContract,
    }
  }

  return { ...base, canUseHzzo: false }
}
