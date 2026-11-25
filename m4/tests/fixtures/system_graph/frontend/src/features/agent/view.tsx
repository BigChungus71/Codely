import { Link } from "react-router-dom";
import { route } from "../../config/path";
const API = "/api/agents";
export function AgentView() {
  fetch(API);
  fetch("/api/unmapped");
  return <Link to={route}>Agents</Link>;
}
