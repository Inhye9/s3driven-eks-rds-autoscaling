#!/bin/bash

export PATH="$PATH:/apps/autoscale/bin"

# 현재 시간 세팅
time=`date +"%Y-%m-%d %H:%M:%S"`
date=${time:0:10}  

# Input Value 확인
echo "----------------------------------------------------------------------"
echo "[autoscale] $(date) Input Value: $1 , whoami: $(whoami)"

#kubectx cluster
/apps/.kubectx/kubectx autoscale-test-cluster
INIT_DESIRED_SCALE=("1" "1" "1")
MIN_DESIRED_SCALE=("3" "3" "3")
QUARTER_DESIRED_SCALE=("5" "5" "5")
HALF_DESIRED_SCALE=("7" "7" "7")
MAX_DESIRED_SCALE=("10" "10" "10")


set_scale_array() {
    case "$1" in
        init)    DESIRED_SCALE=("${INIT_DESIRED_SCALE[@]}") ;;
        min)     DESIRED_SCALE=("${MIN_DESIRED_SCALE[@]}") ;;
        quarter) DESIRED_SCALE=("${QUARTER_DESIRED_SCALE[@]}") ;;
        half)    DESIRED_SCALE=("${HALF_DESIRED_SCALE[@]}") ;;
        *)       DESIRED_SCALE=("${MAX_DESIRED_SCALE[@]}") ;;
    esac
}

# 공통 스케일링 함수
autoscale_hpa_list() {
    local namespace=$1
    shift
    local hpa_list=("$@")

    idx=0
    for HPA_NAME in "${hpa_list[@]}"; do
        echo "[autoscale] Checking HPA for $HPA_NAME in namespace $namespace..."
        HPA_INFO=$(kubectl get hpa "$HPA_NAME" -n "$namespace" -o json)

        CURRENT_MIN_PODS=$(echo "$HPA_INFO" | jq '.spec.minReplicas')
        CURRENT_PODS=$(echo "$HPA_INFO" | jq '.status.currentReplicas')
        DESIRED_POD_SCALE=${DESIRED_SCALE[$idx]}

        echo "[autoscale] HPA_NAME: $HPA_NAME, CURRENT_MIN_PODS: $CURRENT_MIN_PODS, CURRENT_PODS: $CURRENT_PODS, DESIRED_SCALE: $DESIRED_POD_SCALE"

        if [[ "$CURRENT_MIN_PODS" -lt "$CURRENT_PODS" ]]; then
            if [[ "$CURRENT_MIN_PODS" -lt "$DESIRED_POD_SCALE" ]]; then
                echo "[autoscale] scaling $HPA_NAME : $CURRENT_PODS >> $DESIRED_POD_SCALE..."
                kubectl patch hpa "$HPA_NAME" -n "$namespace" -p "{\"spec\":{\"minReplicas\":${DESIRED_POD_SCALE}}}"
            else
                echo "[autoscale] No scaling needed for $HPA_NAME"
            fi
        else
            if [[ "$CURRENT_MIN_PODS" -ne "$DESIRED_POD_SCALE" ]]; then
                echo "[autoscale] $HPA_NAME : $CURRENT_PODS >> $DESIRED_POD_SCALE..."
                kubectl patch hpa "$HPA_NAME" -n "$namespace" -p "{\"spec\":{\"minReplicas\":${DESIRED_POD_SCALE}}}"
            else
                echo "[autoscale] No scaling needed for $HPA_NAME"
            fi
        fi
        idx=$((idx+1))
    done
}

# ==== 실제 실행 ====

# 1. test 네임스페이스 처리
set_scale_array "$1"
autoscale_hpa_list "test" "1-hpa" "2-hpa" "3-hpa"

# 2. istio-system 네임스페이스 처리 (원한다면 다른 스케일 지정도 가능)
ISTIO_DESIRED_SCALE=("5")
DESIRED_SCALE=("${ISTIO_DESIRED_SCALE[@]}")
autoscale_hpa_list "istio-system" "istio-ingressgateway"