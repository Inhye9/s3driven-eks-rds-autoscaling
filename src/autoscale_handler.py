import json
import urllib.parse
import boto3
import csv
import logging
import urllib3
import os
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta 
from botocore.exceptions import WaiterError 


scheduler = boto3.client('scheduler')
ec2_client = boto3.client('ec2')
ssm_client = boto3.client('ssm')
s3 = boto3.client('s3')

lambda_name = 'autoscale_handler.py'
instance_id = '' # kubectl ec2 id 
scheduler_prefix = 'autorun'
osuser = 'appuser'  # kubectl ec2 app os id

# 현재 일자 
#today_date  = datetime.now().date()
# print(today_date.strftime("%Y년 %m월 %d일"))

zonetz = ZoneInfo("Asia/Seoul")
today_date=datetime.now(tz=zonetz)
print(today_date.strftime("%Y년 %m월 %d일"))

# loading 로그 
logging.warning('********************************************************************************')
logging.warning('[START] ' + lambda_name + ' is loading.')

# boto3로 s3 trigger의 data를 received
def lambda_handler(event, context):
    
    # start 로그 
    write_log(1,'')
    print("Received event: " + json.dumps(event, indent=2))

    # Teams로 보낼 결과값 변수
    result_code = 200
    result_msg = ""
    parsed_str = ""
    key = ""
    
    try:
        # event에서 bucket과 key 추출
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
        
        response = s3.get_object(Bucket=bucket, Key=key)
        logging.warning("[INFO] key: " + key)

        # csv 파일명이 맞으면 수행
        if not 'autorun' in key :
          # raise("[Error] The file is not right. Upload autorun-sms.csv on s3://pri-autorun-sms-s3/update_schedule/")
          print("[Error] The file is not right. Upload autorun-sms.csv on s3://pri-autorun-sms-s3/update_schedule/")
          return 
            
        # Body를 line으로 split 함.
        res_body = response.get('Body').read().splitlines() 
        
        # response의 Body값: Byte -> 문자열 형태로 변환.
        # resList = [x.decode(encoding = 'utf-8') for x in resBody ]
        res_list = [x.decode(encoding = 'cp949') for x in res_body ]

        # response의 Body값: 문자열 -> 배열 형태로 변환
        parsed_data, parsed_str = parse_csv(res_list)
        
        # parsed_data를 cron 등록을 위한 형태로 변환
        cronjob = convert_to_crontab_format(parsed_data)
        
        # cron을 workbench에 업로드 
        upload_crontab_on_ec2(cronjob)
        
        # eventbridge_scheduler를 등록 
        generate_eventbridge_scheduler(parsed_data)

        
    # return response['ContentType']
    except Exception as e:
        #logging.error(e)
        #logging.error('[Error] getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(key, bucket))
        result_code = 500
        #result_msg = json.dumps(e).encode('utf-8')
        result_msg+='[Error] ' + str(e)
        logging.error(result_msg)
    # raise e
    
    try:
        # 결과값을 SNS를 활용하여 Teams로 메세지 전송
        send_result_to_teams(result_code, result_msg, parsed_str, key)
        
    except Exception as e:   
        logging.error(e)
    
    # done 로그 
        write_log(2,'')
        logging.warning('********************************************************************************')

## parse_csv: csv를 파싱하는 함수
# 예) 2024,4,2,12,00,13,00 = 2024년 4월 2일 12:00-13:00 
def parse_csv(res_list): 
    parsed_data = [] 
    parsed_str = ""
    
    # 콤마(,)를 기준으로 csv를 파싱. 
    csv_list = csv.reader(res_list, delimiter=',', quotechar='"')
    for idx, row in enumerate(csv_list):
        # idx == 0은 csv의 title이므로 생략한다. 
        if idx == 0:
            continue
        
        if (len(row) < 12) or (len(row) > 14): 
            raise ValueError('[Error] The file on s3 bucket is wrong. The column of File does not match. len(row):' + str(len(row)) +"/14")
        
        event_db = ''
        # event DB 증설여부 세팅
        if row[10] != '':
            event_db = str(row[10]).replace(' ','') 
            event_db = event_db.upper()
        else:
            event_db = "N"
        
        # percentage 세팅 
        if row[11] == '':
            row[11] = 100
        
        # start_time이 현재 시간 이전 -> 생략(증설x)
        start_time = datetime(int(row[0]), int(row[1]), int(row[2]), int(row[3]), int(row[4]))
        outdated = check_outdated(start_time)
     
        if not outdated: 
            parsed_data.append({
                'start_year': int(row[0]),
                'start_month': int(row[1]),
                'start_day': int(row[2]),
                'start_hour': int(row[3]),
                'start_minute': int(row[4]),
                'end_year': int(row[5]),
                'end_month': int(row[6]),
                'end_day': int(row[7]),
                'end_hour': int(row[8]),
                'end_minute': int(row[9]),
                'event_db': event_db,  #Y/N
                'percentage': int(row[11]),
                'title': str(row[12]),
                'register': str(row[13])
            })
        
        # teams 출력 메세지 세팅
        # register 여부 확인 
        if str(row[13]) != '':
            parsed_str += "<br>📌 <b>" + str(row[12]) + "/" + str(row[13]) +"</b>\n"
        else: 
            parsed_str += "<br>📌 <b>" + str(row[12]) + "</b>\n"
        
        parsed_str += "<br>" + "&nbsp;&nbsp;● " +str(row[0])+"년 "+str(row[1])+"월 "+str(row[2])+"일 "+str(row[3])+"시 "+str(row[4])+"분 ~ "
        parsed_str += str(row[5])+"년 "+str(row[6])+"월 "+str(row[7])+"일 "+str(row[8])+"시 "+str(row[9])+"분 "
        
        # # percentage 확인
        # if int(row[11]) == -1:
        #     parsed_str += ",증설 수량: Fixed, EventDB 증설: "+ str(event_db) + "\n<br>"   
        # else:
        #     parsed_str += ",증설 수량: "+ str(row[11]) +"%, EventDB 증설: "+ str(event_db) + "\n<br>"   
        
        # percentage 확인
        if int(row[11]) == -1 and not outdated:
            parsed_str += ",증설 수량: Fixed, EventDB 증설: "+ str(event_db) + "\n<br>"   
        elif outdated: 
            parsed_str += ",증설 수량: X(지난 일자), EventDB 증설: "+ str(event_db) + "\n<br>"   
        else:
            parsed_str += ",증설 수량: "+ str(row[11]) +"%, EventDB 증설: "+ str(event_db) + "\n<br>" 
    
    
    # done 로그 
    write_log(0,'parse_csv')
    return parsed_data, parsed_str; 


## convert_to_crontab_format: parsed_data를 crontab 형식으로 변경하는 함수
def convert_to_crontab_format(parsed_data): 
    #cronjobs = []
    cronjob = ""
    homepath = "/apps/operating-itn"
    logpath = homepath + "/logs/cron_autorun.log 2>&1"
    
    for event in parsed_data:
        start_time = datetime(event['start_year'], event['start_month'], event['start_day'], event['start_hour'], event['start_minute'])
        end_time = datetime(event['end_year'], event['end_month'], event['end_day'], event['end_hour'], event['end_minute'])
        
        p = event['percentage']
        
        # skip
        if p == -1:  
            continue
        
        # 더블마일리지 행사의 경우(3/13, 14, 15, 16):
        d_year = start_time.year
        d_month = start_time.month
        d_day = start_time.day

        # 수요일 아울렛 행사의 경우
        start_weekday = start_time.weekday()
        if start_weekday == 2: 
            if p > 50:
                cronjob += (start_time - timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh max >> " + logpath + " #autoreg" + "\n"
                cronjob += (end_time + timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh half >> " + logpath + " #autoreg" + "\n"
            else: 
                continue
        # 더블마일리지 행사의 경우(3/13, 14, 15, 16):
        elif d_year == 2025 and d_month == 3 and d_day in {13, 14, 15, 16}:
                if p > 50:
                    cronjob += (start_time - timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh max >> " + logpath + " #autoreg" + "\n"
                    cronjob += (end_time + timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh half >> " + logpath + " #autoreg" + "\n"
                else: 
                    continue
        # 다른 요일의 경우(수 제외)
        else: 
            if p > 50:
                cronjob += (start_time - timedelta(minutes=40)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh half >> " + logpath + " #autoreg" +"" "\n"
                cronjob += (start_time - timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh max >> " + logpath + " #autoreg" + "\n"
                cronjob += (end_time + timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh half >> " + logpath + " #autoreg" + "\n"
                cronjob += (end_time + timedelta(minutes=40)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh min >> " + logpath + " #autoreg" + "\n"
            elif 25 < p <= 50 :
                cronjob += (start_time - timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh half >> " + logpath + " #autoreg" + "\n"
                cronjob += (end_time + timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh min >> " + logpath + " #autoreg" + "\n"
            else :
                cronjob += (start_time - timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh quarter >> " + logpath + " #autoreg" + "\n"
                cronjob += (end_time + timedelta(minutes=30)).strftime('%M %H %d %m *')+ osuser + homepath +"/bin/cron_autorun.sh min >> " + logpath + " #autoreg" + "\n"
        
    
    # done 로그 
    write_log(0,'convert_to_crontab_format')
    return cronjob


## upload cronFile on workbench EC2: cronjob 리스트를 EC2에 업로드하는 함수
def upload_crontab_on_ec2(cronjob):
    
    # ec-tag명으로 ec2의 instance_id를 가져온다
    response = ec2_client.describe_instances(
        Filters=[
            {
                'Name': 'tag:Name',
                'Values': ['workbench-ec2'] # workbench-ec2
            }
        ]
    )
    instance_id = response['Reservations'][0]['Instances'][0]['InstanceId']
    print("instance_id:" + str(instance_id))
    
    # ssm을 사용해서 ec2의 instance에 명령 전송 
    # init_crontab.sh: csv 등록일자 기준 이전 cron을 삭제하는 shell
    #exec_shell_path = "/root/workspace/chart/bin"
    exec_shell_path = "/apps/operating-itn/bin"
    response = ssm_client.send_command(
        InstanceIds=[instance_id],
        DocumentName="AWS-RunShellScript",
        TimeoutSeconds=60,
        Parameters={
            'commands': [
                #f"echo '{cronjob}' | sudo tee -a /etc/crontab"
                #f"sudo /root/workspace/chart/bin/init_crontab.sh && echo '{cronjob}' | sudo tee -a /etc/crontab"
                #f"sudo '{exec_shell_path}'/init_crontab.sh && echo '{cronjob}' | sudo tee -a /etc/crontab"
                f"sudo /apps/operating-itn/bin/init_crontab.sh  && echo -n '{cronjob}' | sudo tee -a /etc/crontab" 
            ]
        }
    )
    
     # 명령어 실행 상태를 확인 
    invoCnt = 3
    while 0 < invoCnt < 4 :
        time.sleep(1)  # API 호출 사이에 간격을 두어 상태 업데이트 시간을 보장
        invoCnt-=1
        
        # 명령의 결과를 가져오는 코드
        output = ssm_client.get_command_invocation(
            CommandId=response['Command']['CommandId'],
            InstanceId=instance_id
        )
        status = output['Status'].lower()
        print("inVoCnt:" + str(invoCnt) +", status:" + status)
        
        if status in ['pending', 'inprogress']:
            if invoCnt == 1 : 
                print("upload_crontab_on_ec2.response =" + json.dumps(output, default=str, indent=2))
                raise('[Error] SSM Client failed to load the command to the instance['+instance_id+'] in 3s')
            else:
                continue
        elif status == 'success':
            return
        else:
            print("upload_crontab_on_ec2.response =" + json.dumps(output, default=str, indent=2))
            raise('[Error] SSM Client failed to load the command to the instance['+instance_id+'] in 3s')

    
    # send_command로 전송한 command 실행 종료를 wait
    #print("upload_crontab_on_ec2.response =" + json.dumps(response, default=str, indent=2))

    #if str(response['ResponseMetadata']['HTTPStatusCode']) != '200':
    #  raise('[Error] SSM Client failed to load the command to the instance['+instance_id+']')
    
    # done 로그 
    write_log(0,'upload_crontab_on_ec2')
    
    
## generate_eventbridge_scheduler: eventbridge scheduler를 생성하는 함수
def generate_eventbridge_scheduler(parsed_data):
    
    # csv 등록일자 기준 이전 EventBridge scheduler를 삭제하는 함수
    delete_previous_eventbridge_scheduler()
    
   
    
    # 새로운 EventBridge scheduler를 등록 
    for idx, event in enumerate(parsed_data):
        start_time = datetime(event['start_year'], event['start_month'], event['start_day'], event['start_hour'], event['start_minute'])
        end_time = datetime(event['end_year'], event['end_month'], event['end_day'], event['end_hour'], event['end_minute'])
        
        #Scheduler 시간 산출
        date = start_time.strftime('%Y%m%d-%H')
        add_time_1 = (start_time - timedelta(minutes=60)).strftime('%Y-%m-%dT%H:%M:%S')
        add_time_2 = (start_time - timedelta(minutes=50)).strftime('%Y-%m-%dT%H:%M:%S')
        del_time_1 = (end_time + timedelta(minutes=50)).strftime('%Y-%m-%dT%H:%M:%S')
        del_time_2 = (end_time + timedelta(minutes=60)).strftime('%Y-%m-%dT%H:%M:%S')
        
        
        # 변수 세팅 
        action=""
        time=""
        dbname=""
        dbtype=""
        
        # x: 증설수량 설정, y: eventDB 증설 여부 설정 
        y=1 
        x=0
        
        # skip 
        if int(event['percentage']) == -1: # skip 
            continue

        # '25.03.10 추가> 더블마일리지 행사의 경우(3/13, 14, 15, 16):
        d_year = start_time.year
        d_month = start_time.month
        d_day = start_time.day

        
        # 수요일 아울렛 행사의 경우: 
        start_weekday = start_time.weekday()
        if start_weekday == 2:
            if int(event['percentage']) > 50:  # RDS 1개만 증설 
                x=3
            else: 
                x=1  # skip
                 
            if event['event_db'] == "Y":
                y=3
            else:
                y=2
        # '25.03.10 추가> 더블마일리지 행사의 경우(3/13, 14, 15, 16):
        elif d_year == 2025 and d_month == 3 and d_day in {13, 14, 15, 16}:
            if int(event['percentage']) > 50:  # RDS 1개만 증설 
                x=3
            else: 
                x=1  # skip
                 
            if event['event_db'] == "Y":
                y=3
            else:
                y=2
        # 수요일이 아닌 경우 
        else:
            if int(event['percentage']) > 50:
              x=5 
            else:
              x=3
        
            if event['event_db'] == "Y":
              y=3
            else: 
              y=2 
        
        # scheduler는 설정 시간 1개당 4개 scheduler 등록(2개의 add, 2개의 remove)
        for j in range(1, y):
            if j == 1:
                dbname = "order"
                dbtype = "db.r5.4xlarge"
            elif j == 2: 
                dbname = "event" 
                dbtype = "db.r5.2xlarge"
                    
            for i in range(1, x):
                if i == 1: 
                    action = "add"
                    time = add_time_2
                if i == 2: 
                    action = "remove"
                    time = del_time_1
                if i == 3: 
                    action = "add"
                    time = add_time_1
                if i == 4: 
                    action = "remove"
                    time = del_time_2
            
                schedule_name = scheduler_prefix + dbname +'-read-'+ date + '-' + action +'-'+str(i)
                          
                # scheduler_target을 설정
                scheduler_target = {
                                # Lambda 설정: autorun-managing-rds-reader-lmb
                                'Arn' : 'arn:aws:lambda:ap-northeast-2:206178055504:function:autorun-managing-rds-reader-lmb', 
                                # Role 설정: autorun-managing-rds-reader-schedule-role
                                #'RoleArn': 'arn:aws:iam::206178055504:role/autorun-managing-rds-reader-schedule-role',
                                'RoleArn': 'arn:aws:iam::206178055504:role/service-role/autorun-managing-rds-reader-schedule-role',
                                # Payload 설정
                                'Input': json.dumps({
                                    "identifier" : scheduler_prefix +dbname+"-cluster", 
                                    "action" : action, 
                                    "db_type" : dbtype, 
                                    "quantity" : "1"  
                                }),
                                # RetryPolicy: OFF로 설정
                                'RetryPolicy': {
                                    'MaximumEventAgeInSeconds': 60,
                                    'MaximumRetryAttempts': 0
                                }
                }
            
                try: 
                # evenbridge scheduler 를 생성한다.
                    response = scheduler.create_schedule(
                        #Name = date +'-'+str(i) + '-autorun-order-read-'+ action , 
                        Name = schedule_name, 
                        GroupName = 'autorun-managing-rds-reader-sg',
                        ScheduleExpression = 'at('+time+')',
                        ScheduleExpressionTimezone = 'Asia/Seoul', 
                        FlexibleTimeWindow = {"Mode":"OFF"},
                        Target = scheduler_target,
                        State= 'ENABLED', #DISABLED/ENABLED
                        ActionAfterCompletion = 'NONE',
                    )        
            
                except Exception as e:
                    error_msg = str(e)
                    print(str(e))
                    if (schedule_name + ' already exists' in error_msg):
                        logging.warning ('[Warning] '+ schedule_name + ' already exists.' )
                        continue
                    else:
                        raise(error_msg)
                
    # done 로그 
    write_log(0,'generate_eventbridge_scheduler')

                
# delete_previous_eventbridge_scheduler: 이전 EventBridge Scheduler를 전체 삭제하는 함수
def delete_previous_eventbridge_scheduler():
    
    # 기존 scheduler 목록 조회(스케줄러명: autorun-order-read*)
    response = scheduler.list_schedules(
        GroupName = 'autorun-managing-rds-reader-sg',
        NamePrefix = 'autorun-'
    )
    
    
    # 삭제할 scheduler 있는 지 체크
    if not response['Schedules']:
        logging.warning('There is no previous schedule to delete in response.')
        return 
    
    # 지난 scheduler 전체 삭제 
    scheduler_name_list = [sche ['Name'] for sche in response['Schedules']]
    for name in scheduler_name_list:

        # Eventbridge scheduler 전체 삭제
        response = scheduler.delete_schedule(
            #GroupName = 'autorun-managing-rds-reader-sg',
            GroupName = 'autorun-managing-rds-reader-sg',
            Name = name
        )
        
        # print('delete response:' +json.dumps(response, default=str, indent=2))
        if str(response['ResponseMetadata']['HTTPStatusCode']) != '200':
            raise('[Error] EventBridge Scheduler " + name + " was not deleted.')
    
    # done 로그 
    write_log(0, 'delete_previous_eventbridge_scheduler')
    

# write_log: log를 write 해주는 함수
def write_log(num, function_name): 
    # 0 = done 
    if num == 0:
        logging.warning('[DONE] ' + lambda_name + '.' + function_name +' was done.')
    # 1 = start
    elif num == 1:
        logging.warning('[START] ' + lambda_name + ' is starting.')
    # 2 = finish(완전 종료) 
    elif num == 2: 
        logging.warning('[DONE]' + lambda_name + ' was successfully done. ')
    else:
        return
        

# send_result_to_teams(): 결과를 SNS을 통하여 Teams Webhook으로 전송하는 함수 
def send_result_to_teams(result_code, result_msg, parsed_str, key):
    # 요일별 emoji 가져오기
    emoji, weekday = get_weekday_emoji()
    
    if result_code == 200:
        result_flag = emoji + "✅ [스케줄 등록 완료] <b>" +  today_date.strftime("%Y년 %m월 %d일") + "("+ weekday +") </b>에 등록된 스케줄 목록입니다.  <br><br>"
        # result_flag = "✅ [스케줄 등록 완료] on " + key +"\n"
        # result_msg = "The requested schedules have been registered successfully.<br>"
        result_msg = " "
    else: 
        result_flag = emoji + "💥[스케줄 등록 실패] on" + key +"\n"
        
    # 전송할 메세지 처리
    msg = {
        'text': result_flag + "\n" + result_msg + "\n" + parsed_str
    }
    
    # urllib3으로 http 연결 처리 
    http = urllib3.PoolManager()
    # teams webhook을 가져온다(Lambda>구성>환경변수*)
    url = os.environ['teams_webhook']
    
    # msg를 teams webhook으로 전송
    encoded_msg = json.dumps(msg).encode('utf-8')
    resp = http.request('POST',url, body=encoded_msg)

    
    # done 로그 
    write_log(0, 'send_result_to_teams')

# 현재시간 일자와 input(datetime) 비교    
def check_outdated(date_in):
    today_date = datetime.now()
    
    return today_date > date_in
## /etc/crontab init_cron.sh 필요

def get_weekday_emoji():
    weekday = today_date.weekday()
    
    weekday_emojis = {
    0: "🌞",
    1: "🚀",
    2: "👚",
    3: "📺",
    4: "🙉",
    5: "😎",
    6: "🏄"
    }
    
    weekday_kor = {
    0: "월",
    1: "화",
    2: "수",
    3: "목",
    4: "금",
    5: "토",
    6: "일"
    }
    
    return weekday_emojis[weekday], weekday_kor[weekday] 