#!/usr/bin/env bash
set -euo pipefail
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CTRL="$BASE_DIR/control.sh"

if [[ $# -lt 1 ]]; then
  echo "Usage:"
  echo "  ./easy.sh status [inf_001..inf_010|all]"
  echo "  ./easy.sh nyala [inf|all]"
  echo "  ./easy.sh mati  [inf|all]"
  echo "  ./easy.sh strategi [inf|all] [natural|lembut|closing|endorse]"
  echo "  ./easy.sh nada [inf|all] [warm|formal|tegas]"
  echo "  ./easy.sh followup [inf|all] [lembut|keras|formal]"
  echo "  ./easy.sh ritme [inf|all] [lambat|normal|cepat]"
  echo "  ./easy.sh jadwal [inf|all] [jam_ig] [jam_fb] [jam_report]"
  echo "  ./easy.sh kanal [inf|all] [ig,fb,wa|ig|fb,ig]"
  echo "  ./easy.sh rantai [inf|all] [startHH:MM] [gapMinDetik] [gapMaxDetik] [gapInfluencerDetik]"
  echo "  ./easy.sh paket [inf|all] [santai|normal|agresif] [startHH:MM]"
  exit 1
fi

cmd="$1"
shift || true

target="${1:-all}"

case "$cmd" in
  status)
    "$CTRL" status "$target"
    ;;

  nyala)
    "$CTRL" on "$target"
    ;;

  mati)
    "$CTRL" off "$target"
    ;;

  strategi)
    mode_raw="${2:-natural}"
    case "$mode_raw" in
      natural) preset="story" ;;
      lembut) preset="softsell" ;;
      closing) preset="hardclose" ;;
      endorse) preset="endorse" ;;
      *)
        echo "Mode strategi tidak dikenal: $mode_raw"
        echo "Pilihan: natural | lembut | closing | endorse"
        exit 1
        ;;
    esac
    "$CTRL" strategy "$target" "$preset"
    ;;

  nada)
    tone_raw="${2:-warm}"
    case "$tone_raw" in
      warm) tone="warm" ;;
      formal) tone="formal" ;;
      tegas) tone="hard" ;;
      *)
        echo "Mode nada tidak dikenal: $tone_raw"
        echo "Pilihan: warm | formal | tegas"
        exit 1
        ;;
    esac
    "$CTRL" tone "$target" "$tone"
    ;;

  followup)
    mode="${2:-lembut}"
    case "$mode" in
      lembut|keras|formal) ;;
      *)
        echo "Mode followup tidak dikenal: $mode"
        echo "Pilihan: lembut | keras | formal"
        exit 1
        ;;
    esac
    "$CTRL" followup "$target" "$mode"
    ;;

  ritme)
    pace_raw="${2:-normal}"
    case "$pace_raw" in
      lambat) pace="slow" ;;
      normal) pace="normal" ;;
      cepat) pace="fast" ;;
      *)
        echo "Mode ritme tidak dikenal: $pace_raw"
        echo "Pilihan: lambat | normal | cepat"
        exit 1
        ;;
    esac
    "$CTRL" cadence "$target" "$pace"
    ;;

  jadwal)
    ig="${2:-09:00}"
    fb="${3:-09:30}"
    report="${4:-21:00}"
    "$CTRL" schedule "$target" --ig "$ig" --fb "$fb" --report "$report"
    ;;

  kanal)
    channels="${2:-ig,fb,wa}"
    "$CTRL" channels "$target" "$channels"
    ;;

  rantai)
    start="${2:-09:00}"
    gap_min="${3:-70}"
    gap_max="${4:-130}"
    gap_inf="${5:-80}"
    "$CTRL" chain "$target" --start "$start" --gap-min-sec "$gap_min" --gap-max-sec "$gap_max" --next-inf-gap-sec "$gap_inf"
    ;;

  paket)
    paket_mode="${2:-normal}"
    start="${3:-09:00}"

    case "$paket_mode" in
      santai)
        strategi_mode="story"
        nada_mode="warm"
        followup_mode="lembut"
        ritme_mode="slow"
        gap_min="120"
        gap_max="300"
        gap_inf="180"
        ;;
      normal)
        strategi_mode="story"
        nada_mode="warm"
        followup_mode="lembut"
        ritme_mode="normal"
        gap_min="70"
        gap_max="130"
        gap_inf="80"
        ;;
      agresif)
        strategi_mode="hardclose"
        nada_mode="hard"
        followup_mode="keras"
        ritme_mode="fast"
        gap_min="45"
        gap_max="90"
        gap_inf="60"
        ;;
      *)
        echo "Mode paket tidak dikenal: $paket_mode"
        echo "Pilihan: santai | normal | agresif"
        exit 1
        ;;
    esac

    "$CTRL" strategy "$target" "$strategi_mode"
    "$CTRL" tone "$target" "$nada_mode"
    "$CTRL" followup "$target" "$followup_mode"
    "$CTRL" cadence "$target" "$ritme_mode"
    "$CTRL" chain "$target" --start "$start" --gap-min-sec "$gap_min" --gap-max-sec "$gap_max" --next-inf-gap-sec "$gap_inf"

    echo "paket_applied target=$target mode=$paket_mode start=$start gap=${gap_min}-${gap_max}s next_inf=${gap_inf}s"
    ;;

  *)
    echo "Perintah tidak dikenal: $cmd"
    echo "Gunakan: status | nyala | mati | strategi | nada | followup | ritme | jadwal | kanal | rantai | paket"
    exit 1
    ;;
esac
