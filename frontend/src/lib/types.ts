export interface User {
  id: string;
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  organization_id: string | null;
  is_active: boolean;
}

export interface Organization {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  country: string;
  compliance_policies: string | null;
}

export interface DashboardMetrics {
  total_reviewed: number;
  high_risk: number;
  medium_risk: number;
  low_risk: number;
  pending_approval: number;
  signed: number;
  upcoming_deadlines_count: number;
  upcoming_deadlines: UpcomingDeadline[];
  avg_review_time: number | null;
  hours_saved: number;
}

export interface Contract {
  id: string;
  title: string;
  contract_type: string | null;
  counterparty: string | null;
  status: string;
  risk_score: number | null;
  created_at: string;
  updated_at: string;
}

export interface ContractDetail extends Contract {
  content: string | null;
  file_path: string | null;
  amount: number | null;
  currency: string;
  created_by: string | null;
  signed_at: string | null;
  signed_by: string | null;
  signature: string | null;
  signature_timestamp: string | null;
  certificate_thumbprint: string | null;
}

export interface ContractVersion {
  id: string;
  version_number: number;
  changes_description: string | null;
  created_by: string | null;
  created_at: string;
}

export interface SignRequest {
  request_id: string;
  hash: string;
}

export interface SignConfirm {
  signature: string;
  timestamp: string;
  certificate_thumbprint: string;
}

export interface ContractDeadline {
  id: string;
  contract_id: string;
  deadline_date: string;
  type: string;
  days_left: number;
  is_notified: boolean;
}

export interface UpcomingDeadline {
  id: string;
  contract_id: string;
  contract_title: string;
  deadline_date: string;
  type: string;
  days_left: number;
}

export interface Notification {
  id: string;
  user_id: string;
  contract_id: string | null;
  text: string;
  read_at: string | null;
  created_at: string;
  contract_title: string | null;
}

export const CONTRACT_TYPES: Record<string, string> = {
  purchase: "Купля-продажа",
  lease: "Аренда",
  service: "Подряд / услуги",
  nda: "NDA",
  employment: "Трудовой",
  other: "Другое",
};

export interface ContractList {
  total: number;
  page: number;
  items: Contract[];
}

export interface UserList {
  total: number;
  page: number;
  items: User[];
}

export const ROLE_LABELS: Record<string, string> = {
  admin: "Администратор",
  head: "Руководитель",
  senior_lawyer: "Старший юрист",
  lawyer: "Юрист",
  compliance: "Комплаенс",
  finance: "Финансы",
  external: "Внешний (просмотр)",
};
