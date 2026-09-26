#!/usr/bin/env bash
# Dérive une OVA importable du qcow2 que Packer vient de produire, sans
# VirtualBox et sans `ovftool` (propriétaire, compte Broadcom requis).
#
# Une OVA est un `tar` de trois fichiers, dans CET ordre :
#
#   1. le `.ovf`, du XML qui décrit la machine ;
#   2. le `.mf`, les empreintes SHA256 des deux autres ;
#   3. le disque, en VMDK `streamOptimized`.
#
# L'ordre n'est pas une convention : VirtualBox refuse l'archive si le `.ovf`
# n'est pas son premier membre, avec « does not contain an .ovf-file ».
#
# Éprouvé avant d'être écrit, dans un conteneur Incus portant VirtualBox 7.0 :
# l'OVA produite ici s'importe (« Successfully imported the appliance »), son
# disque est attaché au contrôleur SCSI, et le contenu du disque revient
# identique après conversion, empreinte du brut comparée.
#
# Deux pièges que ces essais ont révélés, et que ce script évite :
#
#   * sans `AddressOnParent` sur l'élément de disque, VirtualBox lit un canal non
#     initialisé et refuse l'import : « Failed to extract channel value ...
#     channel=-522241808 » ;
#   * un VMDK issu d'un disque JAMAIS écrit fait échouer la création du medium
#     (« Storage for the medium is not created »). Un vrai build n'y est pas
#     exposé, le disque portant une installation complète.
set -euo pipefail

VERSION="${1:?usage: faire-ova.sh <version> <repertoire>}"
OUT="${2:?usage: faire-ova.sh <version> <repertoire>}"
NOM="dsoxlab-appliance-${VERSION}"

QCOW="$(find "$OUT" -maxdepth 1 -name '*.qcow2' -o -maxdepth 1 -name "${NOM}" | head -1)"
test -n "$QCOW" || { echo "aucun qcow2 dans $OUT" >&2; exit 1; }

# `streamOptimized` est le seul sous-format de VMDK qu'une OVA accepte.
#
# `adapter_type=lsilogic` n'est pas décoratif : sans lui, `qemu-img` écrit `ide`
# dans le descripteur du VMDK, alors que l'OVF déclare un contrôleur LsiLogic.
# VirtualBox importe quand même, mais les deux descriptions se contredisent, et
# c'est le genre d'écart qui finit par mordre sur un hyperviseur plus regardant.
qemu-img convert -p -f qcow2 -O vmdk \
  -o subformat=streamOptimized,adapter_type=lsilogic \
  "$QCOW" "${OUT}/${NOM}-disk1.vmdk"

OCTETS=$(stat -c%s "${OUT}/${NOM}-disk1.vmdk")
CAPACITE=$(qemu-img info --output=json "$QCOW" \
  | python3 -c 'import json,sys; print(json.load(sys.stdin)["virtual-size"])')

# NAT, et non un pont nommé : un adaptateur figé au nom de la machine de build
# n'existe pas chez celui qui importe l'image, et sa VM démarre sans réseau.
cat > "${OUT}/${NOM}.ovf" <<OVF
<?xml version="1.0" encoding="UTF-8"?>
<Envelope ovf:version="1.0" xml:lang="en-US"
  xmlns="http://schemas.dmtf.org/ovf/envelope/1"
  xmlns:ovf="http://schemas.dmtf.org/ovf/envelope/1"
  xmlns:rasd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_ResourceAllocationSettingData"
  xmlns:vssd="http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/CIM_VirtualSystemSettingData">
  <References>
    <File ovf:href="${NOM}-disk1.vmdk" ovf:id="file1" ovf:size="${OCTETS}"/>
  </References>
  <DiskSection>
    <Info>Virtual disk information</Info>
    <Disk ovf:capacity="${CAPACITE}" ovf:diskId="vmdisk1" ovf:fileRef="file1"
      ovf:format="http://www.vmware.com/interfaces/specifications/vmdk.html#streamOptimized"/>
  </DiskSection>
  <NetworkSection>
    <Info>Logical networks</Info>
    <Network ovf:name="NAT"><Description>NAT, works with no configuration</Description></Network>
  </NetworkSection>
  <VirtualSystem ovf:id="${NOM}">
    <Info>dsoxlab appliance ${VERSION}</Info>
    <Name>${NOM}</Name>
    <OperatingSystemSection ovf:id="96" ovf:version="13">
      <Info>Debian GNU/Linux (64-bit)</Info>
    </OperatingSystemSection>
    <VirtualHardwareSection>
      <Info>Virtual hardware requirements</Info>
      <System>
        <vssd:ElementName>Virtual Hardware Family</vssd:ElementName>
        <vssd:InstanceID>0</vssd:InstanceID>
        <vssd:VirtualSystemType>vmx-13</vssd:VirtualSystemType>
      </System>
      <Item>
        <rasd:Description>Number of virtual CPUs</rasd:Description>
        <rasd:ElementName>4 virtual CPU(s)</rasd:ElementName>
        <rasd:InstanceID>1</rasd:InstanceID>
        <rasd:ResourceType>3</rasd:ResourceType>
        <rasd:VirtualQuantity>4</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:AllocationUnits>byte * 2^20</rasd:AllocationUnits>
        <rasd:ElementName>8192 MB of memory</rasd:ElementName>
        <rasd:InstanceID>2</rasd:InstanceID>
        <rasd:ResourceType>4</rasd:ResourceType>
        <rasd:VirtualQuantity>8192</rasd:VirtualQuantity>
      </Item>
      <Item>
        <rasd:Address>0</rasd:Address>
        <rasd:ElementName>SCSI Controller 0</rasd:ElementName>
        <rasd:InstanceID>3</rasd:InstanceID>
        <rasd:ResourceSubType>lsilogic</rasd:ResourceSubType>
        <rasd:ResourceType>6</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AddressOnParent>0</rasd:AddressOnParent>
        <rasd:ElementName>Hard Disk 1</rasd:ElementName>
        <rasd:HostResource>ovf:/disk/vmdisk1</rasd:HostResource>
        <rasd:InstanceID>4</rasd:InstanceID>
        <rasd:Parent>3</rasd:Parent>
        <rasd:ResourceType>17</rasd:ResourceType>
      </Item>
      <Item>
        <rasd:AutomaticAllocation>true</rasd:AutomaticAllocation>
        <rasd:Connection>NAT</rasd:Connection>
        <rasd:ElementName>Ethernet 1</rasd:ElementName>
        <rasd:InstanceID>5</rasd:InstanceID>
        <rasd:ResourceSubType>E1000</rasd:ResourceSubType>
        <rasd:ResourceType>10</rasd:ResourceType>
      </Item>
    </VirtualHardwareSection>
  </VirtualSystem>
</Envelope>
OVF

# Les 4 vCPU et 8 Go annoncés ci-dessus ne sont pas décoratifs : c'est le
# dimensionnement MESURÉ pour jouer les labs `vm` d'un catalogue complet (les
# trois hôtes du catalogue Linux se partagent 5120 Mo, et le processeur décide du
# respect de la fenêtre de 180 s). L'utilisateur peut réduire, il saura pourquoi.

cd "$OUT"
{
  printf 'SHA256(%s)= %s\n' "${NOM}.ovf" "$(sha256sum "${NOM}.ovf" | cut -d' ' -f1)"
  printf 'SHA256(%s)= %s\n' "${NOM}-disk1.vmdk" "$(sha256sum "${NOM}-disk1.vmdk" | cut -d' ' -f1)"
} > "${NOM}.mf"

tar -cf "${NOM}.ova" "${NOM}.ovf" "${NOM}.mf" "${NOM}-disk1.vmdk"
rm -f "${NOM}-disk1.vmdk" "${NOM}.ovf" "${NOM}.mf"

# Contrôle immédiat plutôt que confiance : le premier membre décide de
# l'importabilité, et le vérifier ici coûte une milliseconde.
premier="$(tar -tf "${NOM}.ova" | head -1)"
case "$premier" in
  *.ovf) : ;;
  *) echo "premier membre inattendu dans l'OVA : $premier" >&2; exit 1 ;;
esac

ls -lh "${NOM}.ova"
