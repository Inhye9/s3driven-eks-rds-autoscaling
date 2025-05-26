#!/bin/bash

# set variables:  current date
current_date=$(date +"%Y%m%d")
current_year=$(date +"%Y")
current_month=$(date +"%m")
current_time=$(date +"%Y%m%d-%H%M%S")
echo "$current_date"

# backup previous /etc/crontab
sudo cp -Rp /etc/crontab /etc/crontab.$current_time

# read each line on  "/etc/crontab" file
while IFS= read -r line; do

       # process a line only including "autorun" word
        if [[ $line == *"#autoreg"* ]]; then

                # delete previous cron (standard: current date)
                extract=$(echo "$line" | cut -c 1-14)
                sudo sed -i "{ /#autoreg/ d}" /etc/crontab
        fi

done < /etc/crontab
