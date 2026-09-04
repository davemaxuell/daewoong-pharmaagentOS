package main

workload_kinds := {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}

pod_spec := input.spec.jobTemplate.spec.template.spec if {
  input.kind == "CronJob"
}

pod_spec := input.spec.template.spec if {
  input.kind != "CronJob"
}

containers := object.get(pod_spec, "containers", [])

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  not regex.match("@sha256:[a-f0-9]{64}$", container.image)
  message := sprintf("%s/%s container %s must use an immutable sha256 image digest", [input.kind, input.metadata.name, container.name])
}

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  object.get(object.get(container, "securityContext", {}), "allowPrivilegeEscalation", true) != false
  message := sprintf("%s/%s container %s must disable privilege escalation", [input.kind, input.metadata.name, container.name])
}

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  object.get(object.get(container, "securityContext", {}), "readOnlyRootFilesystem", false) != true
  message := sprintf("%s/%s container %s must use a read-only root filesystem", [input.kind, input.metadata.name, container.name])
}

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  not "ALL" in object.get(object.get(object.get(container, "securityContext", {}), "capabilities", {}), "drop", [])
  message := sprintf("%s/%s container %s must drop ALL capabilities", [input.kind, input.metadata.name, container.name])
}

deny contains message if {
  input.kind in workload_kinds
  object.get(object.get(pod_spec, "securityContext", {}), "runAsNonRoot", false) != true
  message := sprintf("%s/%s must run as non-root", [input.kind, input.metadata.name])
}

deny contains message if {
  input.kind in workload_kinds
  object.get(object.get(object.get(pod_spec, "securityContext", {}), "seccompProfile", {}), "type", "") != "RuntimeDefault"
  message := sprintf("%s/%s must use the RuntimeDefault seccomp profile", [input.kind, input.metadata.name])
}

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  object.get(object.get(object.get(container, "resources", {}), "requests", {}), "cpu", "") == ""
  message := sprintf("%s/%s container %s must set CPU requests", [input.kind, input.metadata.name, container.name])
}

deny contains message if {
  input.kind in workload_kinds
  some container in containers
  object.get(object.get(object.get(container, "resources", {}), "limits", {}), "memory", "") == ""
  message := sprintf("%s/%s container %s must set memory limits", [input.kind, input.metadata.name, container.name])
}
