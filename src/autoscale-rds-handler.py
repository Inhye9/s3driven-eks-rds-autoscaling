import boto3
import os

def lambda_handler(event, context):
    client = boto3.client('rds', region_name='ap-northeast-2')
    # 스케쥴 설정 시 Eventbridge 상에서 모든 설정을 마칠 수 있도록 Eventbridge에서 Lambda를 호출할 때 아래와 같은 증설/축소 정보를 Payload에 포함합니다.
    # {"identifier":"mzc-prd-order-cluster", "action":"add", "db_type":"db.r6g.large", "quantity":"2"}
    cluster_identifier = event['identifier']
    action = event['action']
    db_type = event['db_type']
    if 'db.' not in db_type:
        db_type = 'db.' + db_type
    quantity = int(event['quantity'])
    
    readers = describe_rds_clusters(client, cluster_identifier)
    
    try:
        if action == 'add':
            add_reader_instance(client, cluster_identifier, db_type, quantity, readers)
        elif action == 'remove':
            remove_reader_instance(client, cluster_identifier, db_type, quantity, readers)
    except Exception as e:
        print(f"Error! : {e}")


def describe_rds_clusters(client, cluster_identifier):
    response = client.describe_db_clusters(DBClusterIdentifier=cluster_identifier)
    cluster_members = response['DBClusters'][0]['DBClusterMembers']

    readers = []
    for i in cluster_members:
        if not i["IsClusterWriter"]:
            readers.append(i["DBInstanceIdentifier"])
    
    print(f'리더 인스턴스 List : {readers}')    ### DEBUGGING ###
    return readers
        
        
def add_reader_instance(client, cluster_identifier, db_type, quantity, readers):
    response = client.describe_db_instances(DBInstanceIdentifier=readers[-1])
    db_pg_name = response['DBInstances'][0]['DBParameterGroups'][0]['DBParameterGroupName']
    
    instance_num = len(readers) + 1 # 1 : writer

    # add reader
    for cnt in range(quantity):
        instance_num += 1
        instance_identifier = f"{cluster_identifier}-instance-{instance_num}"
        try:
            response = client.create_db_instance(
                DBClusterIdentifier = cluster_identifier,
                DBInstanceIdentifier = instance_identifier,
                DBInstanceClass = db_type,
                DBParameterGroupName = db_pg_name,
                Engine = 'aurora-postgresql',
                AutoMinorVersionUpgrade = False,
                EnablePerformanceInsights = True,
                PromotionTier = 2
            )
        except Exception as e:
            print(f"Error! : {e}")
        print(f"**Create reader instance** : {instance_identifier}")


def remove_reader_instance(client, cluster_identifier, db_type, quantity, readers):
    # 현재 실행 중인 모든 리더 인스턴스의 상태와 타입을 체크
    check_readers = []
    for id in readers:
        response = client.describe_db_instances(DBInstanceIdentifier = id)
        if response['DBInstances'][0]['DBInstanceStatus'] == 'available' and response['DBInstances'][0]['DBInstanceClass'] == db_type:
            check_readers.append(id)

    # 리더 인스턴스가 최소 2개 실행 중인지 체크
    check_readers.sort() # 리스트 내 정렬
    print(f'정렬된 리더 인스턴스 List : {check_readers}')    ### DEBUGGING ###

    if len(check_readers) - quantity < 1:
        raise Exception("At least two read instances must be running.")
    
    else:    
        # 생성시간이 최신인 인스턴스 기준으로 수량에 맞게 삭제
        remove_readers = check_readers[-quantity:]
        print(f'삭제 대상으로 선정한 리더 인스턴스 : {remove_readers}')    ### DEBUGGING ###
        
        # remove reader
        try:
            for instance_identifier in remove_readers:
                response = client.delete_db_instance(
                    DBInstanceIdentifier = instance_identifier,
                    SkipFinalSnapshot = True
                )
                print(f"**Remove reader instance** : {instance_identifier}")
        except Exception as e:
            print(f"Error! : {e}")